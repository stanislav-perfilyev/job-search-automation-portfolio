import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ApplicationWindow {
    id: root
    visible: true
    width: 420
    height: 320
    title: "System Monitor"
    color: "#1a1a2e"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 20

        Text {
            text: "System Monitor"
            color: "#e0e0ff"
            font.pixelSize: 22
            font.bold: true
            Layout.alignment: Qt.AlignHCenter
        }

        // CPU gauge
        GaugeItem {
            label: "CPU"
            value: systemStats.cpuPercent
            color: value > 80 ? "#ff4444" : value > 50 ? "#ffaa00" : "#44ff88"
            Layout.fillWidth: true
        }

        // Memory gauge
        GaugeItem {
            label: "RAM  " + systemStats.memUsedMB + " / " + systemStats.memTotalMB + " MB"
            value: systemStats.memPercent
            color: value > 85 ? "#ff4444" : value > 60 ? "#ffaa00" : "#44aaff"
            Layout.fillWidth: true
        }

        // Uptime
        Text {
            text: "Uptime: " + systemStats.uptimeStr
            color: "#aaaacc"
            font.pixelSize: 14
            Layout.alignment: Qt.AlignHCenter
        }
    }

    // Reusable gauge component (defined inline via Component)
    component GaugeItem: ColumnLayout {
        required property string label
        required property int    value
        required property color  color

        Text {
            text: label + "  " + value + "%"
            color: "#ccccee"
            font.pixelSize: 14
        }

        Rectangle {
            Layout.fillWidth: true
            height: 28
            radius: 6
            color: "#2a2a4a"

            Rectangle {
                width: parent.width * (value / 100.0)
                height: parent.height
                radius: parent.radius
                color: parent.parent.color

                Behavior on width {
                    NumberAnimation { duration: 300; easing.type: Easing.OutCubic }
                }
            }

            Text {
                anchors.centerIn: parent
                text: value + "%"
                color: "#ffffff"
                font.pixelSize: 12
                font.bold: true
            }
        }
    }
}
