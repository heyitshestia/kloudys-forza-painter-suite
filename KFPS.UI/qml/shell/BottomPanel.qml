import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    property string mode: "log"
    property bool collapsed: false
    property bool compactActions: Theme.logical(width) < 850
    signal toggle()

    strong: true
    radius: Theme.px(13)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.px(8)
        spacing: Theme.px(5)

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.px(30)
            Layout.minimumHeight: Layout.preferredHeight
            spacing: Theme.px(8)

            Icon {
                name: root.mode === "changelog" ? "changelog" : "terminal"
                iconSize: Theme.px(15)
                glow: true
                Layout.alignment: Qt.AlignVCenter
            }

            Text {
                text: root.mode === "changelog" ? "Changelog" : "Live runtime log"
                color: Theme.primaryBright
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(11.5)
                font.weight: Font.DemiBold
                verticalAlignment: Text.AlignVCenter
                Layout.alignment: Qt.AlignVCenter
            }

            Item { Layout.fillWidth: true }

            GhostButton {
                visible: root.mode === "changelog"
                dense: true
                text: "Refresh Notes"
                iconName: "refresh"
                minimumWidth: Theme.px(84)
                toolTipText: "Reload the local patch notes shown in this panel."
                onClicked: changelogService.refresh()
            }

            GhostButton {
                visible: root.mode === "log"
                dense: true
                text: "Clear"
                minimumWidth: Theme.px(62)
                toolTipText: "Clear the visible runtime log from this panel. Log files on disk are not deleted."
                onClicked: logs.clear()
            }

            GhostButton {
                visible: root.mode === "log"
                dense: true
                text: root.compactActions ? "Logs" : "Open logs folder"
                iconName: "folder"
                minimumWidth: Theme.px(root.compactActions ? 72 : 126)
                toolTipText: "Open the folder containing KFPS runtime log files."
                onClicked: desktop.openRuntime()
            }

            GhostButton {
                dense: true
                text: root.collapsed ? "⌃" : "⌄"
                minimumWidth: Theme.px(36)
                maximumTextWidth: Theme.px(20)
                toolTipText: root.collapsed ? "Expand this panel." : "Collapse this panel."
                onClicked: root.toggle()
            }
        }

        Loader {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.collapsed
            sourceComponent: root.mode === "changelog" ? changelogComp : logComp
        }
    }

    Component {
        id: changelogComp

        ListView {
            id: changes
            clip: true
            model: changelogService.model
            spacing: Theme.px(1)

            delegate: Item {
                required property string version
                required property string summary
                width: changes.width
                height: Theme.px(27)

                RowLayout {
                    anchors.fill: parent
                    spacing: Theme.px(16)

                    Text {
                        Layout.preferredWidth: Theme.px(54)
                        Layout.minimumWidth: Layout.preferredWidth
                        text: version
                        color: Theme.success
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.px(10)
                        font.weight: Font.DemiBold
                        verticalAlignment: Text.AlignVCenter
                    }

                    Text {
                        Layout.fillWidth: true
                        text: summary
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(10.2)
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
        }
    }

    Component {
        id: logComp

        ListView {
            id: list
            clip: true
            model: logs.model
            spacing: 0
            onCountChanged: positionViewAtEnd()

            delegate: Item {
                required property string line
                required property string level
                width: list.width
                height: Theme.px(22)

                Text {
                    anchors.fill: parent
                    text: line
                    color: level === "error" ? Theme.danger
                                             : (level === "warning" ? Theme.warning : Theme.muted)
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.px(10.2)
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
            }

            ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
        }
    }
}
