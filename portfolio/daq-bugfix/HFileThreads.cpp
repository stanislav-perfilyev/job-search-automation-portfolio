
// =============================================================================
// HFileThreads.cpp
// =============================================================================
// USB download and file-write threads for the EDR5COM portable DAQ instrument.
//
// Two thread classes are implemented here:
//   HUdfFileWriteThread  — downloads accelerometer data and writes a UDF file
//   HExportFileWriteThread — downloads the same data and exports as UTF-16 CSV
//
// Both threads communicate with the USB layer via Qt signals/slots and protect
// shared state with a QMutex + QWaitCondition pair (mutex / bufferFilled).
//
// Bug-fix history (June 2026)
// ---------------------------
// BUG-1  Double-free in cleanup()
//   cleanup() called delete[] on data_buffer / event_buffer but did NOT set
//   the pointers to nullptr. If addRecorder() was called more than once, a
//   second cleanup() call saw non-null dangling pointers and attempted a
//   second delete → undefined behaviour / crash.
//   Fix: always null-out a pointer immediately after delete[].
//
// BUG-2  Partial allocation leak on std::bad_alloc
//   Inside the impact-event loop the three float arrays (xAxis, yAxis, zAxis)
//   and the four slow-track arrays are allocated in a try block. If allocation
//   of the second or third array threw bad_alloc, only the first array was
//   already heap-allocated. The catch handler called break without cleaning up,
//   so those bytes leaked for the remainder of the process lifetime.
//   Fix: delete[] / nullptr every partially allocated pointer in each catch.
//
// Additional improvements
// -----------------------
// * NULL → nullptr throughout (C++11 type-safe null).
// * logfile is nulled after fclose() to prevent use-after-close.
// * Added section comments and clarified the streaming protocol.
// =============================================================================

#include <iostream>
#include <float.h>
#include <math.h>
#include "TextIndex.h"
#include "HSettings.h"
#include "HFileThreads.h"

extern HSettings *Settings;

// Enable USB streaming path (vs. block-by-block read path).
// When defined, data is pushed via got_stream() signal; otherwise the thread
// emits reqReadBlock() and waits for each block individually.
#define __STREAM_USB__

// =============================================================================
//  HUdfFileWriteThread  —  downloads DAQ data and produces a UDF file
// =============================================================================

// -----------------------------------------------------------------------------
// Constructor
// -----------------------------------------------------------------------------
HUdfFileWriteThread::HUdfFileWriteThread(QObject *parent)
    : QThread(parent)
{
    udfFile    = nullptr;
    setup      = nullptr;
    running    = false;
    logfile    = nullptr;
    usb_comm   = nullptr;

    // Accelerometer axis buffers — allocated per-impact-event in run()
    xAxis      = nullptr;
    yAxis      = nullptr;
    zAxis      = nullptr;

    // Slow-track channel buffers — allocated once per recorder in run()
    slwIntTemp  = nullptr;
    slwExtTemp  = nullptr;
    slwBattery  = nullptr;
    slwHumidity = nullptr;

    // Download buffers — allocated in setupThread(), freed by cleanup()
    event_buffer  = nullptr;
    data_buffer   = nullptr;
    recorder_num  = 0;
    which_temperature = 0;

    logfile = fopen("edr_download.log", "a");
}

// -----------------------------------------------------------------------------
// Destructor — stops the thread before releasing resources
// -----------------------------------------------------------------------------
HUdfFileWriteThread::~HUdfFileWriteThread()
{
    running = false;          // signal run() to exit its loops
    bufferFilled.wakeAll();   // unblock any pending wait()
    wait();                   // join the thread

    // BUG-1 note: cleanup() is NOT called here intentionally because the
    // destructor already owns the definitive delete. Using delete[] on a
    // nullptr is well-defined (no-op), so no null-check is needed.
    delete [] data_buffer;
    delete [] event_buffer;

    // Axis buffers should be nullptr here (deleted at the end of each
    // impact-event iteration in run()), but guard defensively.
    delete [] xAxis;
    delete [] yAxis;
    delete [] zAxis;

    if (udfFile) delete udfFile;
    udfFile = nullptr;

    if (logfile) fclose(logfile);
}

// -----------------------------------------------------------------------------
// resetThread — stops the running thread without destroying the object
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::resetThread(void)
{
    running = false;
    bufferFilled.wakeAll();
    wait();
}

// -----------------------------------------------------------------------------
// setUsbCom — wire up the USB layer; must be called before startThread()
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::setUsbCom(HUSBComm *comm)
{
    usb_comm = comm;
    connect(usb_comm, SIGNAL(got_stream(char *)),
            this,     SLOT(fillStreamBuffer(char *)));
}

// -----------------------------------------------------------------------------
// cleanup — FIX BUG-1: free download buffers and null the pointers so that
//           repeated calls (via addRecorder()) cannot double-free.
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::cleanup(void)
{
    // delete[] on nullptr is a no-op, so the null-check is not required.
    // Nulling immediately after delete prevents any dangling-pointer access.
    delete [] data_buffer;
    data_buffer = nullptr;

    delete [] event_buffer;
    event_buffer = nullptr;
}

// -----------------------------------------------------------------------------
// initFile — open / create the output UDF file
// -----------------------------------------------------------------------------
bool HUdfFileWriteThread::initFile(const char *filename,
                                    const char *message,
                                    int num_recorders,
                                    int which_temp)
{
    udfFile = new HUdfFile();
    // Note: operator new throws std::bad_alloc on failure in C++; it never
    // returns nullptr. The guard below is kept for defensive clarity but is
    // effectively unreachable without a try/catch wrapper.
    if (udfFile == nullptr) return false;

    if (logfile)
        fprintf(logfile, "Starting download of file %s\n", filename);

    which_temperature = which_temp;
    return udfFile->openUDFFile(filename, message, num_recorders);
}

// -----------------------------------------------------------------------------
// addRecorder — prepare for the next recorder's data; resets download buffers
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::addRecorder(int recorder)
{
    active_recorder = recorder;
    cleanup();   // BUG-1 fix: pointers are nulled inside cleanup()
    udfFile->addRecorder(recorder_num++);
}

// -----------------------------------------------------------------------------
// setupFileInfo — populate calibration, job, and slow-track configuration
// -----------------------------------------------------------------------------
bool HUdfFileWriteThread::setupFileInfo(unitCfg_t   *cfg,
                                         edrCal_t    *cal,
                                         edrJobDesc_t *job_desc,
                                         edrJobSetup_t *rcp)
{
    if (udfFile == nullptr) return false;
    if (!udfFile->setUserDocs(job_desc))                    return false;
    if (!udfFile->setCalibrationInfo(active_recorder, cfg, cal, rcp)) return false;
    if (!udfFile->setRCPInfo(active_recorder, rcp, cal))    return false;

    setup = rcp;

    // Build a bitmask of which slow-track channels are active
    slwTrackMask = 0;
    if (rcp->job_control_flags & CF_SLOWTRK_ITMP_M) slwTrackMask |= 0x01;
    if (rcp->job_control_flags & CF_SLOWTRK_ETMP_M) slwTrackMask |= 0x02;
    if (rcp->job_control_flags & CF_SLOWTRK_BATT_M) slwTrackMask |= 0x04;
    if (rcp->job_control_flags & CF_SLOWTRK_HUM_M)  slwTrackMask |= 0x08;

    udfFile->getConversions(
        ((rcp->job_control_flags & CF_INT_EXT_ACC_M) ? true : false),
        &xMult, &yMult, &zMult);

    return true;
}

// -----------------------------------------------------------------------------
bool HUdfFileWriteThread::openRecorderStream(unitCfg_t *cfg)
{
    if (udfFile == nullptr) return false;
    return udfFile->openRecorderStream(cfg);
}

// -----------------------------------------------------------------------------
// setupThread — calculate buffer sizes and allocate download buffers.
//               event_buffer holds all event tags; data_buffer receives one
//               block at a time (non-streaming path) or acts as a bounce buffer.
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::setupThread(unsigned int start_ndx,
                                       unsigned int end_ndx,
                                       unsigned int total_blocks)
{
    // Align indices to block boundaries
    job_start_index = start_ndx & (~(EVENTS_PER_BLOCK - 1));
    job_end_index   = end_ndx   & (~(EVENTS_PER_BLOCK - 1));

    int event_size;
    if (job_end_index > job_start_index)
    {
        event_size = (job_end_index - job_start_index) * EVENT_TAG_SIZE;
    }
    else
    {
        // Circular buffer wrap-around
        event_size = ((EVENT_LBA_END - job_start_index) + job_end_index) * EVENT_TAG_SIZE;
    }

    num_events   = event_size / EVENT_TAG_SIZE;
    event_buffer = new unsigned char[event_size + 512]; // +512 = one spare block
    job_blocks   = total_blocks + event_size / 512;
    data_buffer  = new unsigned char[1024 + 64];        // two-block bounce buffer

    if (logfile)
        fprintf(logfile, "Event tag indices - start: %d  end %d\n", start_ndx, end_ndx);
}

// -----------------------------------------------------------------------------
void HUdfFileWriteThread::closeFile(void)
{
    if (udfFile == nullptr) return;
    udfFile->closeFile();
}

unsigned int HUdfFileWriteThread::getTotalBlocks(void)
{
    return job_blocks;
}

bool HUdfFileWriteThread::startThread(void)
{
    running = true;
    start(LowPriority);
    return true;
}

// -----------------------------------------------------------------------------
// fillBuffer — non-streaming path: called from the main thread to push one block
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::fillBuffer(unsigned char *buffer)
{
    memcpy((void *)dest_ptr, (void *)buffer, SD_DEFAULT_BLOCK_SIZE);
    bufferFilled.wakeAll();
}

// -----------------------------------------------------------------------------
// fillStreamBuffer — streaming path: called via got_stream() signal.
//
// Protocol:
//   1. run() increments bufferwait before calling wait(), signals readiness.
//   2. fillStreamBuffer() spins until bufferwait > 0, then sets dest_ptr to
//      the newly arrived buffer and wakes run().
//   3. run() processes the buffer and decrements strm_blks.
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::fillStreamBuffer(char *buffer)
{
    // Wait until run() has incremented bufferwait (i.e. is ready to receive)
    uint16_t waitbuf;
    do
    {
        mutex.lock();
        waitbuf = bufferwait;
        mutex.unlock();
    }
    while (waitbuf == 0);

    dest_ptr = (unsigned char *)buffer;
    bufferFilled.wakeAll();

    stream_count -= 2;
    if (stream_count < 12)
        stream_count = 0;
}

// -----------------------------------------------------------------------------
void HUdfFileWriteThread::cancelWrite(void)
{
    if (usb_comm) usb_comm->cancelStream();
    running = false;
    bufferFilled.wakeAll();
    if (logfile) fprintf(logfile, "Write cancelled\n");
}

// =============================================================================
// run() — main download loop
//
// Phase 1: read all event tags into event_buffer.
// Phase 2: count on/off blocks, impact events, slow-track events.
// Phase 3: for each on/off block, stream impact data and slow-track data,
//           writing each to the UDF file.
// =============================================================================
void HUdfFileWriteThread::run(void)
{
    eventTag_t *event_ptr;
    int blocks = 0;
    uint32_t index = job_start_index;
    dest_ptr = (unsigned char *)event_buffer;
    uint32_t lba_end;
    int timeout_count = 0;

    // ------------------------------------------------------------------
    // Phase 1: read all event tags
    // ------------------------------------------------------------------
    while (index != job_end_index)
    {
        emit reqReadBlock(active_recorder, (unsigned int)(index / EVENTS_PER_BLOCK));
        mutex.lock();
        bufferFilled.wait(&mutex);
        mutex.unlock();

        if (!running) break;

        index += EVENTS_PER_BLOCK;
        if (index == EVENT_LBA_END) index = 0; // circular wrap
        dest_ptr += SD_DEFAULT_BLOCK_SIZE;
        blocks++;
        if ((blocks % 8) == 0) emit percentComplete(blocks);
    }

    if (!running) return;

    // ------------------------------------------------------------------
    // Phase 2: tally event types
    // ------------------------------------------------------------------
    int num_onoff   = 0;
    int num_impact  = 0;
    int num_slwtrk  = 0;
    int num_channel_sets = 0;

    for (int i = 0; i < num_events; i++)
    {
        if (!running) break;
        event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
        logEvent(i, event_ptr);

        switch (event_ptr->event_type & 0x0f)
        {
        case EVENT_TYPE_JOB_START:
            num_onoff++;
            break;
        case EVENT_TYPE_IMPACT_EVENT:
            num_impact++;
            break;
        case EVENT_TYPE_SLWTRK_EVENT:
            if (num_slwtrk == 0) extractEventConditions(event_ptr);
            num_slwtrk++;
            break;
        default:
            break;
        }
    }

    if (logfile)
        fprintf(logfile,
                "\n All event tags read: num_onoff = %d  num_slowtrk = %d  num_impact = %d\n",
                num_onoff, num_slwtrk, num_impact);

    // Derive channel-set count and guard against empty recordings
    if (num_impact) num_channel_sets++;
    if (num_slwtrk) num_channel_sets++;
    if ((num_onoff == 0) && num_channel_sets) num_onoff = 1;

    if ((num_onoff == 0) || (num_channel_sets == 0))
    {
        running = false;
        emit some_error(FILETHREAD_ERROR_NO_EVENTS);
        if (logfile) fclose(logfile);
        logfile = nullptr;
        return;
    }

    udfFile->setNumberOfChannelSets(num_channel_sets);
    udfFile->setNumberOfOnOffBlocks(num_onoff);

    // ------------------------------------------------------------------
    // Phase 3: per-on/off block processing
    // ------------------------------------------------------------------
    int      start_job_ndx = 0;
    int      stop_job_ndx  = 0;
    uint32_t start_job_time;
    uint32_t stop_job_time;
    int      total_impact_events = 0;
    int      total_overwrites    = 0;
    bool     err = false;

    if (blocks % 2) blocks++; // keep block count even for streaming

    for (int onoff = 0; onoff < num_onoff; onoff++)
    {
        if (logfile) fprintf(logfile, "On-Off Block %d\n", onoff + 1);

        // Locate JOB_START tag
        for (int i = start_job_ndx; i < num_events; i++)
        {
            event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
            if ((event_ptr->event_type & 0x0f) == EVENT_TYPE_JOB_START)
            {
                start_job_ndx = i;
                start_job_time = event_ptr->event_time;
                if (logfile) fprintf(logfile, "Found job start tag = %d\n", start_job_ndx);
                break;
            }
        }

        // Locate JOB_STOP tag
        stop_job_ndx = 0;
        for (int i = start_job_ndx; i < num_events; i++)
        {
            event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
            if ((event_ptr->event_type & 0x0f) == EVENT_TYPE_JOB_STOP)
            {
                stop_job_ndx = i;
                stop_job_time = event_ptr->event_time;
                if (logfile) fprintf(logfile, "Found job stop tag %d\n", stop_job_ndx);
                break;
            }
        }
        if (stop_job_ndx == 0) stop_job_ndx = num_events;

        total_overwrites += processWindowMode(start_job_ndx, stop_job_ndx);

        udfFile->setOnOffBlkInfo(onoff, start_job_time, stop_job_time, num_impact);

        // --------------------------------------------------------------
        // Impact-event sub-loop
        // --------------------------------------------------------------
        if (num_impact)
        {
            num_impact_events = 0;

            for (int i = start_job_ndx; i < stop_job_ndx; i++)
            {
                if (!running) break;
                event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];

                if ((event_ptr->event_type & 0x0f) == EVENT_TYPE_SLWTRK_EVENT)
                    extractEventConditions(event_ptr);

                if ((event_ptr->event_type & 0x0f) != EVENT_TYPE_IMPACT_EVENT)
                    continue;

                numSamples = event_ptr->accel_data_ptr.num_samples;
                if (numSamples <= 0) continue;

                int skip = (event_ptr->skip_count) / 2;

                // ----------------------------------------------------------
                // Allocate per-event axis buffers
                // BUG-2 FIX: on bad_alloc clean up any partially allocated
                // arrays before exiting the loop — otherwise those bytes leak
                // for the rest of the process lifetime.
                // ----------------------------------------------------------
                try
                {
                    xAxis = new float[numSamples + 2 * SAMPLES_PER_BLOCK];
                    yAxis = new float[numSamples + 2 * SAMPLES_PER_BLOCK];
                    zAxis = new float[numSamples + 2 * SAMPLES_PER_BLOCK];
                }
                catch (std::bad_alloc &)
                {
                    // Free whatever was allocated before the exception
                    delete [] xAxis; xAxis = nullptr;
                    delete [] yAxis; yAxis = nullptr;
                    delete [] zAxis; zAxis = nullptr;

                    if (logfile)
                        fprintf(logfile, "Allocation error: numSamples=%ld\n",
                                (long)numSamples);
                    emit some_error(FILETHREAD_ERROR_BAD_ALLOC);
                    err     = true;
                    running = false;
                    break;
                }

                index    = event_ptr->accel_data_ptr.lba_start;
                dest_ptr = data_buffer;
                sampleCounter      = 0;
                firstPostTrigSample = 0;
                inPreTrig           = false;
                lba_end = event_ptr->accel_data_ptr.lba_start
                          + (numSamples / SAMPLES_PER_BLOCK);
                if (numSamples % SAMPLES_PER_BLOCK) lba_end++;

#ifndef __STREAM_USB__
                // Block-by-block path (non-streaming)
                while (index <= lba_end)
                {
                    mutex.lock();
                    emit reqReadBlock(active_recorder, (unsigned int)index);
                    bufferFilled.wait(&mutex);
                    mutex.unlock();
                    if (!running) break;
                    index++;
                    processBuffer((short *)data_buffer, skip);
                    if (sampleCounter >= numSamples) break;
                    skip = 0;
                    blocks++;
                    if ((blocks % 8) == 0) emit percentComplete(blocks);
                }
#else
                // USB streaming path — request strm_blks blocks at once
                uint32_t strm_blks = (uint32_t)(lba_end - event_ptr->accel_data_ptr.lba_start);
                if (strm_blks % 2) strm_blks++;  // keep even
                strm_blks += 2;                   // +2 guard blocks

                stream_count = strm_blks;
                bufferwait   = 0;
                emit reqStreamBlocks(active_recorder,
                                     (unsigned int)index,
                                     (unsigned int)strm_blks);

                bool wok;
                while (strm_blks)
                {
                    mutex.lock();
                    bufferwait++;
                    wok = bufferFilled.wait(&mutex, 1000); // 1-second timeout
                    bufferwait--;
                    mutex.unlock();

                    if (usb_comm) usb_comm->streamProcessComplete();
                    if (!wok) timeout_count++;
                    if (!running) break;
                    if (!wok) continue;

                    if (sampleCounter < numSamples)
                        processBuffer((short *)dest_ptr, skip);
                    else break;

                    skip = 0;

                    if (sampleCounter < numSamples)
                        processBuffer((short *)(dest_ptr + 512), skip);
                    else break;

                    strm_blks -= 2;
                    blocks    += 2;
                    if ((blocks % 8) == 0) emit percentComplete(blocks);
                }
                if (usb_comm) usb_comm->cancelStream();
#endif

                if (running)
                {
                    if (event_ptr->psevent1 == 0)
                        running = udfFile->saveEvent(num_impact_events++,
                                                     numSamples,
                                                     firstPostTrigSample,
                                                     event_ptr,
                                                     xAxis, yAxis, zAxis);
                    else
                        running = savePsuedoEvents(event_ptr,
                                                   udfFile->getSampleRate(),
                                                   xAxis, yAxis, zAxis);
                }

                // Release axis buffers; pointers nulled to prevent destructor
                // from attempting a second delete if we exit early
                delete [] xAxis; xAxis = nullptr;
                delete [] yAxis; yAxis = nullptr;
                delete [] zAxis; zAxis = nullptr;
            }

            udfFile->setNumberOfImpactEvents(num_impact_events);
            total_impact_events += num_impact_events;
        }

        if (err) break;

        // --------------------------------------------------------------
        // Slow-track sub-loop
        // --------------------------------------------------------------
        if (num_slwtrk)
        {
            running = udfFile->setSlowTrackChanInfo(slwTrackMask, num_channel_sets - 1);
            num_slwtrk_samples = 0;

            // BUG-2 FIX (slow-track): same partial-allocation guard as above
            try
            {
                slwIntTemp  = new float[num_events];
                slwExtTemp  = new float[num_events];
                slwBattery  = new float[num_events];
                slwHumidity = new float[num_events];
            }
            catch (std::bad_alloc &)
            {
                delete [] slwIntTemp;  slwIntTemp  = nullptr;
                delete [] slwExtTemp;  slwExtTemp  = nullptr;
                delete [] slwBattery;  slwBattery  = nullptr;
                delete [] slwHumidity; slwHumidity = nullptr;

                emit some_error(FILETHREAD_ERROR_BAD_ALLOC);
                err     = true;
                running = false;
                break;
            }

            for (int i = start_job_ndx; i < stop_job_ndx; i++)
            {
                if (!running) break;
                event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
                if ((event_ptr->event_type & 0x0f) == EVENT_TYPE_SLWTRK_EVENT)
                {
                    slwIntTemp [num_slwtrk_samples] = Settings->convertInternalTemp(
                                                        event_ptr->slowtrack_data.internal_temp);
                    slwExtTemp [num_slwtrk_samples] = Settings->convertExternalTemp(
                                                        event_ptr->slowtrack_data.external_temp);
                    slwBattery [num_slwtrk_samples] = Settings->convertBatteryReading(
                                                        event_ptr->slowtrack_data.battery_voltage);
                    slwHumidity[num_slwtrk_samples] = Settings->convertHumidity(
                                                        event_ptr->slowtrack_data.humidity);
                    num_slwtrk_samples++;
                }
            }

            udfFile->saveSlowTrackSamples(slwTrackMask, num_slwtrk_samples,
                                           slwIntTemp, slwExtTemp,
                                           slwBattery, slwHumidity);

            delete [] slwIntTemp;  slwIntTemp  = nullptr;
            delete [] slwExtTemp;  slwExtTemp  = nullptr;
            delete [] slwBattery;  slwBattery  = nullptr;
            delete [] slwHumidity; slwHumidity = nullptr;
        }

        udfFile->closeOnOffBlock();
        start_job_ndx = stop_job_ndx;
    }

    udfFile->closeRecorderStream(total_impact_events, num_onoff);
    emit finishedWriting();
    if (total_overwrites) emit sig_overwrites(total_overwrites);

    if (logfile)
    {
        fclose(logfile);
        logfile = nullptr; // prevent use-after-close
    }
}

// -----------------------------------------------------------------------------
// processBuffer — convert raw 16-bit ADC samples to floating-point g-values.
//
// The buffer layout is [X0, Y0, Z0, X1, Y1, Z1, ...] (interleaved).
// buffer[255] == 0x44bb is the pre-trigger sentinel written by the firmware.
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::processBuffer(short *buffer, int skip)
{
    if (buffer[255] == 0x44bb)
    {
        inPreTrig = true;
    }
    else
    {
        if (inPreTrig)
        {
            firstPostTrigSample = sampleCounter;
            inPreTrig = false;
        }
    }

    int i = 0;
    for (int sample = 0; sample < (SAMPLES_PER_BLOCK - (skip / 3)); sample++)
    {
        xAxis[sampleCounter] = (float)((double)buffer[i + skip]     * xMult);
        yAxis[sampleCounter] = (float)((double)buffer[i + skip + 1] * yMult);
        zAxis[sampleCounter] = (float)((double)buffer[i + skip + 2] * zMult);
        sampleCounter++;
        i += 3;
    }
}

// -----------------------------------------------------------------------------
// processWindowMode — enforce the maximum-events-per-window limit by erasing
//                     the lowest-impulse events that exceed the quota.
// Returns the number of events overwritten.
// -----------------------------------------------------------------------------
int HUdfFileWriteThread::processWindowMode(int start, int num_events)
{
    if (setup == nullptr) return 0;
    if ((setup->job_control_flags & CF_WINDOW_MODE_M) == 0) return 0;
    if (num_events < setup->events_per_window) return 0;

    int total_overwrites = 0;
    eventTag_t *event_ptr;
    uint32_t window_end   = job_start_time + setup->time_per_window;
    int win_strt_ndx      = start;
    int win_end_ndx       = num_events;
    int events_in_window  = 0;
    int i, j;
    int current_window    = 0;
    bool processing       = true;

    while (processing)
    {
        events_in_window = 0;
        for (i = win_strt_ndx; i < num_events; i++)
        {
            event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
            if ((event_ptr->event_type & 0x0f) != EVENT_TYPE_IMPACT_EVENT) continue;

            if (event_ptr->current_window == current_window)
            {
                events_in_window++;
            }
            else
            {
                win_end_ndx = i;
                break;
            }
        }
        if (i == num_events) processing = false;

        if (events_in_window > setup->events_per_window)
        {
            int num_overwrites = events_in_window - setup->events_per_window;
            total_overwrites += num_overwrites;
            if (num_overwrites > setup->overwrite_limit)
                num_overwrites = setup->overwrite_limit;

            // Remove the events with the smallest impulse response
            int    min_event  = win_strt_ndx;
            double impulse;
            for (j = 0; j < num_overwrites; j++)
            {
                double min_impulse = 1e10;
                for (int k = win_strt_ndx; k < win_end_ndx; k++)
                {
                    event_ptr = (eventTag_t *)&event_buffer[k * EVENT_TAG_SIZE];
                    if ((event_ptr->event_type & 0x0f) != EVENT_TYPE_IMPACT_EVENT) continue;

                    impulse = (double)event_ptr->impulse;
                    if (impulse < min_impulse)
                    {
                        min_impulse = impulse;
                        min_event   = k;
                    }
                }
                // Mark the selected event as erased
                event_ptr = (eventTag_t *)&event_buffer[min_event * EVENT_TAG_SIZE];
                event_ptr->event_type = 0;
            }
        }

        win_strt_ndx = win_end_ndx;
        win_end_ndx  = num_events;
        window_end  += setup->time_per_window;
        current_window++;
    }
    return total_overwrites;
}

// -----------------------------------------------------------------------------
// savePsuedoEvents — a single impact-data block may contain multiple logically
//                    distinct "pseudo events" packed end-to-end.  This function
//                    splits them and saves each one individually.
// -----------------------------------------------------------------------------
bool HUdfFileWriteThread::savePsuedoEvents(eventTag_t *event_ptr,
                                            double sr,
                                            float xdata[],
                                            float ydata[],
                                            float zdata[])
{
    if (sr == 0.0) return false;

    double   event_time        = (double)event_ptr->event_time
                                + ((double)event_ptr->event_ms / 1000.0);
    uint32_t samples_remaining = numSamples - event_ptr->psevent1;
    // Back-calculate the end time of the first pseudo event
    event_time -= ((double)samples_remaining / sr);
    event_ptr->event_time = (uint32_t)(floor(event_time));
    event_ptr->event_ms   = (uint16_t)((event_time - floor(event_time)) * 1000);

    uint32_t expected_events = 0;
    if (event_ptr->pscount)
        expected_events = numSamples / event_ptr->pscount;
    if (expected_events > 2000)
        emit sig_start_write(expected_events);

    bool     retval      = udfFile->saveEvent(num_impact_events++,
                                               event_ptr->psevent1,
                                               firstPostTrigSample,
                                               event_ptr, xdata, ydata, zdata);
    uint32_t event_start = event_ptr->psevent1;
    uint32_t num_samples;

    while (samples_remaining && retval)
    {
        num_samples = (samples_remaining > event_ptr->pscount)
                      ? event_ptr->pscount
                      : samples_remaining;

        event_time += ((double)num_samples / sr);
        event_ptr->event_time = (uint32_t)(floor(event_time));
        event_ptr->event_ms   = (uint16_t)((event_time - floor(event_time)) * 1000);

        retval = udfFile->saveEvent(num_impact_events++, num_samples, 0,
                                    event_ptr,
                                    &xdata[event_start],
                                    &ydata[event_start],
                                    &zdata[event_start]);

        if ((num_impact_events % 16) == 0)
            emit sig_write_progress(num_impact_events);

        samples_remaining -= num_samples;
        event_start       += num_samples;
        if (!running) break;
    }
    return retval;
}

// -----------------------------------------------------------------------------
// extractEventConditions — read temperature and battery voltage from a
//                          slow-track event and store them in the UDF file.
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::extractEventConditions(eventTag_t *comp_event)
{
    if (udfFile == nullptr) return;

    double temperature = which_temperature
        ? Settings->convertExternalTemp(comp_event->slowtrack_data.external_temp)
        : Settings->convertInternalTemp(comp_event->slowtrack_data.internal_temp);

    double voltage = Settings->convertBatteryReading(
                        comp_event->slowtrack_data.battery_voltage);

    udfFile->setEventConditionData(temperature, voltage);
}

// -----------------------------------------------------------------------------
// writeToDownloadLog — append a single line to the log, re-opening in append
//                      mode each time so the file is flushed to disk promptly.
// -----------------------------------------------------------------------------
void HUdfFileWriteThread::writeToDownloadLog(char *str)
{
    if (logfile)
    {
        fprintf(logfile, "%s\n", str);
        fclose(logfile);
        logfile = nullptr; // null after close to prevent use-after-close
    }
    logfile = fopen("edr_download.log", "a");
}

// -----------------------------------------------------------------------------
// logEvent — write a human-readable description of one event tag to the log.
// Returns false if logfile is not open.
// -----------------------------------------------------------------------------
bool HUdfFileWriteThread::logEvent(int ndx, eventTag_t *event_ptr)
{
    if (logfile == nullptr) return false;

    QDateTime datetime;
    QString   workerStr;

    switch (event_ptr->event_type & 0x0f)
    {
    case EVENT_TYPE_JOB_START:
        datetime  = QDateTime::fromTime_t(event_ptr->event_time + Settings->getTimeZero());
        workerStr = datetime.toString("dd-MMM-yyyy hh:mm:ss");
        fprintf(logfile, "%d  Job Start Event: %s\n",
                ndx, workerStr.toAscii().data());
        break;

    case EVENT_TYPE_JOB_STOP:
        datetime  = QDateTime::fromTime_t(event_ptr->event_time + Settings->getTimeZero());
        workerStr = datetime.toString("dd-MMM-yyyy hh:mm:ss");
        fprintf(logfile, "%d  Job Stop Event: %s\n",
                ndx, workerStr.toAscii().data());
        break;

    case EVENT_TYPE_SLWTRK_EVENT:
        datetime  = QDateTime::fromTime_t(event_ptr->event_time + Settings->getTimeZero());
        workerStr = datetime.toString("dd-MMM-yyyy hh:mm:ss");
        fprintf(logfile, "%d  SlowTrack Event: %s\n",
                ndx, workerStr.toAscii().data());
        break;

    case EVENT_TYPE_IMPACT_EVENT:
        datetime  = QDateTime::fromTime_t(event_ptr->event_time + Settings->getTimeZero());
        workerStr = datetime.toString("dd-MMM-yyyy hh:mm:ss");
        fprintf(logfile, "%d  Impact Event: %s:%4.4f\n",
                ndx, workerStr.toAscii().data(),
                (double)event_ptr->event_ms / 1024.0);
        fprintf(logfile, "  Start Block: %ld  Num Samples: %ld\n",
                (long)event_ptr->accel_data_ptr.lba_start,
                (long)event_ptr->accel_data_ptr.num_samples);
        break;

    default:
        break;
    }
    return true;
}


// =============================================================================
//  HExportFileWriteThread  —  downloads DAQ data and exports as UTF-16 CSV
// =============================================================================

// -----------------------------------------------------------------------------
// Constructor
// -----------------------------------------------------------------------------
HExportFileWriteThread::HExportFileWriteThread(QObject *parent)
    : QThread(parent)
{
    setup      = nullptr;
    running    = false;
    usb_comm   = nullptr;

    xAxis      = nullptr;
    yAxis      = nullptr;
    zAxis      = nullptr;
    event_buffer  = nullptr;
    data_buffer   = nullptr;
    recorder_num  = 0;
    export_file   = nullptr;
    no_event_headers = false;
    recorder_sn[0]   = 0;
}

// -----------------------------------------------------------------------------
// Destructor
// -----------------------------------------------------------------------------
HExportFileWriteThread::~HExportFileWriteThread()
{
    running = false;
    bufferFilled.wakeAll();
    wait();

    delete [] data_buffer;
    delete [] event_buffer;

    if (export_file)
    {
        export_file->close();
        delete export_file;
        export_file = nullptr;
    }
}

// -----------------------------------------------------------------------------
void HExportFileWriteThread::resetThread(void)
{
    running = false;
    bufferFilled.wakeAll();
    wait();
}

// -----------------------------------------------------------------------------
void HExportFileWriteThread::setUsbCom(HUSBComm *comm)
{
    usb_comm = comm;
    connect(usb_comm, SIGNAL(got_stream(char *)),
            this,     SLOT(fillStreamBuffer(char *)));
}

// -----------------------------------------------------------------------------
// cleanup — BUG-1 FIX (export thread): same double-free fix as UDF thread.
// -----------------------------------------------------------------------------
void HExportFileWriteThread::cleanup(void)
{
    delete [] data_buffer;
    data_buffer = nullptr;

    delete [] event_buffer;
    event_buffer = nullptr;
}

// -----------------------------------------------------------------------------
bool HExportFileWriteThread::initFile(const char *filename,
                                       int recorder_num,
                                       bool headers,
                                       int units)
{
    export_file = new QFile(filename);
    if (!export_file->open(QIODevice::WriteOnly | QIODevice::Text)) return false;
    active_recorder  = recorder_num;
    no_event_headers = !headers;
    accel_units      = units;
    return true;
}

// -----------------------------------------------------------------------------
void HExportFileWriteThread::addRecorder(int recorder)
{
    active_recorder = recorder;
    cleanup(); // BUG-1 fix: pointers nulled inside cleanup()
}

// -----------------------------------------------------------------------------
bool HExportFileWriteThread::setupFileInfo(unitCfg_t    *cfg,
                                            edrCal_t     *cal,
                                            edrJobDesc_t *job_desc,
                                            edrJobSetup_t *rcp)
{
    if (export_file == nullptr) return false;

    double sample_rate = 0.0;

    memcpy((void *)recorder_sn, cfg->serial_number, 16);
    recorder_sn[15] = 0;

    if (rcp->job_control_flags & CF_INT_EXT_ACC_M)
    {
        if (rcp->sample_interval)
            sample_rate = 1.0 / ((double)rcp->sample_interval / 1e6);

        double range0 = Settings->expectedRange(cal->sens[0], rcp->gains[0]);
        double range1 = Settings->expectedRange(cal->sens[1], rcp->gains[1]);
        double range2 = Settings->expectedRange(cal->sens[2], rcp->gains[2]);

        xMult = Settings->calcResolution(range0);
        yMult = Settings->calcResolution(range1);
        zMult = Settings->calcResolution(range2);

        if (accel_units == UNITS_MSEC2)
        {
            xMult *= G_TO_MSEC2;
            yMult *= G_TO_MSEC2;
            zMult *= G_TO_MSEC2;
        }
    }
    else
    {
        if ((rcp->sample_interval >= 0) &&
            (rcp->sample_interval < NUM_ADXL357_RATES))
            sample_rate = Settings->getAdxl357Rate(rcp->sample_interval);

        xMult = Settings->getAdxl357Range(rcp->range);
        if (accel_units == UNITS_MSEC2) xMult *= G_TO_MSEC2;
        yMult = xMult;
        zMult = xMult;
    }

    theSampleRate = sample_rate;
    return true;
}

// -----------------------------------------------------------------------------
void HExportFileWriteThread::setupThread(unsigned int start_ndx,
                                          unsigned int end_ndx,
                                          unsigned int total_blocks)
{
    job_start_index = start_ndx & (~(EVENTS_PER_BLOCK - 1));
    job_end_index   = end_ndx   & (~(EVENTS_PER_BLOCK - 1));

    int event_size;
    if (job_end_index > job_start_index)
        event_size = (job_end_index - job_start_index) * EVENT_TAG_SIZE;
    else
        event_size = ((EVENT_LBA_END - job_start_index) + job_end_index) * EVENT_TAG_SIZE;

    num_events   = event_size / EVENT_TAG_SIZE;
    event_buffer = new unsigned char[event_size + 512];
    job_blocks   = total_blocks + event_size / 512;
    data_buffer  = new unsigned char[1024 + 64];
}

// -----------------------------------------------------------------------------
void HExportFileWriteThread::closeFile(void)
{
    if (export_file == nullptr) return;
    export_file->close();
    delete export_file;
    export_file = nullptr;
}

unsigned int HExportFileWriteThread::getTotalBlocks(void)
{
    return job_blocks;
}

bool HExportFileWriteThread::startThread(void)
{
    running = true;
    start(LowPriority);
    return true;
}

// -----------------------------------------------------------------------------
void HExportFileWriteThread::fillBuffer(unsigned char *buffer)
{
    memcpy((void *)dest_ptr, (void *)buffer, SD_DEFAULT_BLOCK_SIZE);
    bufferFilled.wakeAll();
}

// -----------------------------------------------------------------------------
void HExportFileWriteThread::fillStreamBuffer(char *buffer)
{
    uint16_t waitbuf;
    do
    {
        mutex.lock();
        waitbuf = bufferwait;
        mutex.unlock();
    }
    while (waitbuf == 0);

    dest_ptr = (unsigned char *)buffer;
    bufferFilled.wakeAll();
    stream_count -= 2;
    if (stream_count < 12) stream_count = 0;
}

// -----------------------------------------------------------------------------
void HExportFileWriteThread::cancelWrite(void)
{
    if (usb_comm) usb_comm->cancelStream();
    running = false;
    bufferFilled.wakeAll();
}

// -----------------------------------------------------------------------------
// run() — export thread main loop (mirrors HUdfFileWriteThread::run structure)
// -----------------------------------------------------------------------------
void HExportFileWriteThread::run(void)
{
    eventTag_t *event_ptr;
    int blocks = 0;
    uint32_t index = job_start_index;
    dest_ptr = (unsigned char *)event_buffer;
    uint32_t lba_end;

    // Phase 1: read all event tags
    while (index != job_end_index)
    {
        emit reqReadBlock(active_recorder, (unsigned int)(index / EVENTS_PER_BLOCK));
        mutex.lock();
        bufferFilled.wait(&mutex);
        mutex.unlock();
        if (!running) break;
        index += EVENTS_PER_BLOCK;
        if (index == EVENT_LBA_END) index = 0;
        dest_ptr += SD_DEFAULT_BLOCK_SIZE;
        blocks++;
        if ((blocks % 8) == 0) emit percentComplete(blocks);
    }

    if (!running) return;

    // Phase 2: tally event types
    int num_onoff  = 0;
    int num_impact = 0;
    int num_channel_sets = 0;

    for (int i = 0; i < num_events; i++)
    {
        if (!running) break;
        event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
        if ((event_ptr->event_type & 0x0f) == EVENT_TYPE_JOB_START)  num_onoff++;
        else if ((event_ptr->event_type & 0x0f) == EVENT_TYPE_IMPACT_EVENT) num_impact++;
    }

    if (num_impact) num_channel_sets++;
    if ((num_onoff == 0) && num_channel_sets) num_onoff = 1;

    if ((num_onoff == 0) || (num_channel_sets == 0))
    {
        running = false;
        emit some_error(FILETHREAD_ERROR_NO_EVENTS);
        return;
    }

    QTextStream export_strm(export_file);
    export_strm.setCodec("UTF-16");

    number_of_onoff_blocks = num_onoff;
    base_time = -1;

    // Write file header
    if (!no_event_headers)
    {
        QString str;
        QDateTime datetime;

        str = Settings->getText(TEXT_EXPORT_FILE_HEADER1);
        export_strm << str << endl;

        str = Settings->getText(TEXT_EXPORT_FILE_HEADER2);
        datetime = QDateTime::currentDateTime();
        str += datetime.toString(" dd-MMM-yyyy hh:mm:ss");
        export_strm << str << endl;

        str  = Settings->getText(TEXT_EXPORT_FILE_HEADER3);
        str += QString(" ") + QString(recorder_sn);
        export_strm << str << endl;

        str = QString(Settings->getText(TEXT_EXPORT_FILE_HEADER4)).arg(num_impact);
        export_strm << str << endl;

        str = QString(Settings->getText(TEXT_EXPORT_FILE_HEADER5)).arg(theSampleRate, 0, 'f', 2);
        export_strm << str << endl;
    }

    int start_job_ndx = 0;
    int stop_job_ndx  = 0;
    uint32_t start_job_time;
    uint32_t stop_job_time;
    int  total_impact_events = 0;
    int  total_overwrites    = 0;
    bool err = false;

    if (blocks % 2) blocks++;

    // Phase 3: per-on/off block processing
    for (int onoff = 0; onoff < num_onoff; onoff++)
    {
        onoff_blocknum = onoff;

        for (int i = start_job_ndx; i < num_events; i++)
        {
            event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
            if ((event_ptr->event_type & 0x0f) == EVENT_TYPE_JOB_START)
            {
                start_job_ndx  = i;
                start_job_time = event_ptr->event_time;
                break;
            }
        }

        stop_job_ndx = 0;
        for (int i = start_job_ndx; i < num_events; i++)
        {
            event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
            if ((event_ptr->event_type & 0x0f) == EVENT_TYPE_JOB_STOP)
            {
                stop_job_ndx  = i;
                stop_job_time = event_ptr->event_time;
                break;
            }
        }
        if (stop_job_ndx == 0) stop_job_ndx = num_events;

        total_overwrites += processWindowMode(start_job_ndx, stop_job_ndx);

        if (num_impact)
        {
            num_impact_events = 0;

            for (int i = start_job_ndx; i < stop_job_ndx; i++)
            {
                if (!running) break;
                event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
                if ((event_ptr->event_type & 0x0f) != EVENT_TYPE_IMPACT_EVENT) continue;

                numSamples = event_ptr->accel_data_ptr.num_samples;
                if (numSamples <= 0) continue;

                int skip = (event_ptr->skip_count) / 2;

                // BUG-2 FIX: clean up partial allocations on bad_alloc
                try
                {
                    xAxis = new float[numSamples + 2 * SAMPLES_PER_BLOCK];
                    yAxis = new float[numSamples + 2 * SAMPLES_PER_BLOCK];
                    zAxis = new float[numSamples + 2 * SAMPLES_PER_BLOCK];
                }
                catch (std::bad_alloc &)
                {
                    delete [] xAxis; xAxis = nullptr;
                    delete [] yAxis; yAxis = nullptr;
                    delete [] zAxis; zAxis = nullptr;

                    emit some_error(FILETHREAD_ERROR_BAD_ALLOC);
                    err     = true;
                    running = false;
                    break;
                }

                index    = event_ptr->accel_data_ptr.lba_start;
                dest_ptr = data_buffer;
                sampleCounter       = 0;
                firstPostTrigSample = 0;
                inPreTrig           = false;
                lba_end = event_ptr->accel_data_ptr.lba_start
                          + (numSamples / SAMPLES_PER_BLOCK);
                if (numSamples % SAMPLES_PER_BLOCK) lba_end++;

                uint32_t strm_blks = (uint32_t)(lba_end - event_ptr->accel_data_ptr.lba_start);
                if (strm_blks % 2) strm_blks++;
                strm_blks += 2;

                stream_count = strm_blks;
                bufferwait   = 0;
                emit reqStreamBlocks(active_recorder,
                                     (unsigned int)index,
                                     (unsigned int)strm_blks);

                bool wok;
                while (strm_blks)
                {
                    mutex.lock();
                    bufferwait++;
                    wok = bufferFilled.wait(&mutex, 1000);
                    bufferwait--;
                    mutex.unlock();

                    if (usb_comm) usb_comm->streamProcessComplete();
                    if (!running) break;
                    if (!wok) continue;

                    if (sampleCounter < numSamples)
                        processBuffer((short *)dest_ptr, skip);
                    else break;

                    skip = 0;

                    if (sampleCounter < numSamples)
                        processBuffer((short *)(dest_ptr + 512), skip);
                    else break;

                    strm_blks -= 2;
                    blocks    += 2;
                    if ((blocks % 8) == 0) emit percentComplete(blocks);
                }
                if (usb_comm) usb_comm->cancelStream();

                if (running)
                {
                    if (event_ptr->psevent1 == 0)
                        running = saveEvent(export_strm, num_impact_events++,
                                            numSamples, event_ptr->event_time,
                                            xAxis, yAxis, zAxis);
                    else
                        running = savePsuedoEvents(export_strm, event_ptr,
                                                   theSampleRate,
                                                   xAxis, yAxis, zAxis);
                }

                delete [] xAxis; xAxis = nullptr;
                delete [] yAxis; yAxis = nullptr;
                delete [] zAxis; zAxis = nullptr;
            }
            total_impact_events += num_impact_events;
        }

        if (err) break;
        start_job_ndx = stop_job_ndx;
    }

    emit finishedWriting();
    if (total_overwrites) emit sig_overwrites(total_overwrites);
}

// -----------------------------------------------------------------------------
void HExportFileWriteThread::processBuffer(short *buffer, int skip)
{
    if (buffer[255] == 0x44bb)
    {
        inPreTrig = true;
    }
    else
    {
        if (inPreTrig)
        {
            firstPostTrigSample = sampleCounter;
            inPreTrig = false;
        }
    }

    int i = 0;
    for (int sample = 0; sample < (SAMPLES_PER_BLOCK - (skip / 3)); sample++)
    {
        xAxis[sampleCounter] = (float)((double)buffer[i + skip]     * xMult);
        yAxis[sampleCounter] = (float)((double)buffer[i + skip + 1] * yMult);
        zAxis[sampleCounter] = (float)((double)buffer[i + skip + 2] * zMult);
        sampleCounter++;
        i += 3;
    }
}

// -----------------------------------------------------------------------------
int HExportFileWriteThread::processWindowMode(int start, int num_events)
{
    if (setup == nullptr) return 0;
    if ((setup->job_control_flags & CF_WINDOW_MODE_M) == 0) return 0;
    if (num_events < setup->events_per_window) return 0;

    int total_overwrites = 0;
    eventTag_t *event_ptr;
    uint32_t window_end  = job_start_time + setup->time_per_window;
    int win_strt_ndx     = start;
    int win_end_ndx      = num_events;
    int events_in_window = 0;
    int i, j;
    int current_window   = 0;
    bool processing      = true;

    while (processing)
    {
        events_in_window = 0;
        for (i = win_strt_ndx; i < num_events; i++)
        {
            event_ptr = (eventTag_t *)&event_buffer[i * EVENT_TAG_SIZE];
            if ((event_ptr->event_type & 0x0f) != EVENT_TYPE_IMPACT_EVENT) continue;
            if (event_ptr->current_window == current_window)
                events_in_window++;
            else
            {
                win_end_ndx = i;
                break;
            }
        }
        if (i == num_events) processing = false;

        if (events_in_window > setup->events_per_window)
        {
            int num_overwrites = events_in_window - setup->events_per_window;
            total_overwrites += num_overwrites;
            if (num_overwrites > setup->overwrite_limit)
                num_overwrites = setup->overwrite_limit;

            int    min_event = win_strt_ndx;
            double impulse;
            for (j = 0; j < num_overwrites; j++)
            {
                double min_impulse = 1e10;
                for (int k = win_strt_ndx; k < win_end_ndx; k++)
                {
                    event_ptr = (eventTag_t *)&event_buffer[k * EVENT_TAG_SIZE];
                    if ((event_ptr->event_type & 0x0f) != EVENT_TYPE_IMPACT_EVENT) continue;
                    impulse = (double)event_ptr->impulse;
                    if (impulse < min_impulse) { min_impulse = impulse; min_event = k; }
                }
                event_ptr = (eventTag_t *)&event_buffer[min_event * EVENT_TAG_SIZE];
                event_ptr->event_type = 0;
            }
        }

        win_strt_ndx = win_end_ndx;
        win_end_ndx  = num_events;
        window_end  += setup->time_per_window;
        current_window++;
    }
    return total_overwrites;
}

// -----------------------------------------------------------------------------
bool HExportFileWriteThread::savePsuedoEvents(QTextStream   &strm,
                                               eventTag_t    *event_ptr,
                                               double         sr,
                                               float xdata[], float ydata[], float zdata[])
{
    if (sr == 0.0) return false;

    double   event_time        = (double)event_ptr->event_time
                                + ((double)event_ptr->event_ms / 1000.0);
    uint32_t samples_remaining = numSamples - event_ptr->psevent1;
    event_time -= ((double)samples_remaining / sr);
    event_ptr->event_time = (uint32_t)(floor(event_time));
    event_ptr->event_ms   = (uint16_t)((event_time - floor(event_time)) * 1000);

    uint32_t expected_events = 0;
    if (event_ptr->pscount)
        expected_events = numSamples / event_ptr->pscount;
    if (expected_events > 2000)
        emit sig_start_write(expected_events);

    bool     retval      = saveEvent(strm, num_impact_events++,
                                     event_ptr->psevent1, event_ptr->event_time,
                                     xdata, ydata, zdata);
    uint32_t event_start = event_ptr->psevent1;
    uint32_t num_samples;

    while (samples_remaining && retval)
    {
        num_samples = (samples_remaining > event_ptr->pscount)
                      ? event_ptr->pscount
                      : samples_remaining;

        event_time += ((double)num_samples / sr);
        event_ptr->event_time = (uint32_t)(floor(event_time));
        event_ptr->event_ms   = (uint16_t)((event_time - floor(event_time)) * 1000);

        retval = saveEvent(strm, num_impact_events++, num_samples,
                           event_ptr->event_time,
                           &xdata[event_start], &ydata[event_start], &zdata[event_start]);

        if ((num_impact_events % 16) == 0)
            emit sig_write_progress(num_impact_events);

        samples_remaining -= num_samples;
        event_start       += num_samples;
        if (!running) break;
    }
    return retval;
}

// -----------------------------------------------------------------------------
// saveEvent — write one event's header and sample data to the export stream
// -----------------------------------------------------------------------------
bool HExportFileWriteThread::saveEvent(QTextStream &strm,
                                        int event_num,
                                        uint32_t num_samples,
                                        uint32_t event_time,
                                        float xAxis[], float yAxis[], float zAxis[])
{
    if (theSampleRate == 0.0) return false;

    QDateTime datetime;
    QString   str;
    QChar     comma(',');
    QChar     tab('\t');

    double time  = 0.0;
    double delta = 1.0 / theSampleRate;

    if (!no_event_headers)
    {
        strm << endl;

        str = QString(Settings->getText(TEXT_EXPORT_EVENT_HEADER1))
                  .arg(event_num + 1).arg(onoff_blocknum + 1);
        strm << str << endl;

        datetime.setTimeSpec(Qt::UTC);
        datetime = QDateTime::fromTime_t(event_time + Settings->getTimeZero());
        str  = Settings->getText(TEXT_EXPORT_EVENT_HEADER2);
        str += datetime.toString(" dd-MMM-yyyy hh:mm:ss");
        strm << str << endl;

        str = QString(Settings->getText(TEXT_EXPORT_EVENT_HEADER3)).arg(num_samples);
        strm << str << endl;

        strm << Settings->getText(TEXT_EXPORT_EVENT_HEADER4) << endl;
        strm << Settings->getText(TEXT_EXPORT_EVENT_HEADER5) << endl;
        strm << Settings->getText(TEXT_EXPORT_EVENT_HEADER6) << endl;

        str = (accel_units == UNITS_MSEC2)
              ? Settings->getText(TEXT_EXPORT_EVENT_HEADER8)
              : Settings->getText(TEXT_EXPORT_EVENT_HEADER7);
        strm << str << endl;
    }
    else
    {
        if (base_time < 0)
        {
            base_time = event_time;
            time = 0.0;
        }
        else
        {
            time = (double)(event_time - base_time);
        }
    }

    // Write sample rows: time, X, Y, Z (scientific notation, 6 decimal places)
    for (int sample = 0; sample < (int)num_samples; sample++)
    {
        strm << QString("%1").arg(time, 0, 'e', 6) << comma << tab
             << QString("%1").arg(xAxis[sample], 0, 'e', 6) << comma << tab
             << QString("%1").arg(yAxis[sample], 0, 'e', 6) << comma << tab
             << QString("%1").arg(zAxis[sample], 0, 'e', 6) << endl;
        time += delta;
    }

    return true;
}
