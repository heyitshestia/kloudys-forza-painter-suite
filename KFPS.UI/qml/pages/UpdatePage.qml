import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Dialogs 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent

    FastScrollView {
        id: scroll
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            height: Math.max(scroll.availableHeight, implicitHeight)

            Item {
                Layout.fillHeight: true
            }

            HoverCard {
                id: updateCard
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: Math.min(scroll.availableWidth - Theme.px(40), Theme.px(620))
                Layout.minimumWidth: Math.min(scroll.availableWidth - Theme.px(40), Theme.px(360))
                Layout.preferredHeight: Theme.px(440)
                Layout.minimumHeight: Layout.preferredHeight
                strong: true
                padding: Theme.px(20)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(14)

                    Icon {
                        name: "update"
                        iconSize: Theme.px(56)
                        Layout.alignment: Qt.AlignHCenter
                    }

                    Text {
                        text: "Update KFPS"
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(26)
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                        Layout.alignment: Qt.AlignHCenter
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "KFPS closes before updating so Windows can safely replace the executable. Generated images, editor projects, JSON outputs, and runtime data remain preserved by the existing updater."
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(12)
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                        lineHeight: 1.35
                    }

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(58)
                        soft: true

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(14)

                            Text {
                                text: "Current version"
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12)
                                Layout.alignment: Qt.AlignVCenter
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            Text {
                                text: "v" + versionService.localVersion
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(16)
                                font.weight: Font.DemiBold
                                Layout.alignment: Qt.AlignVCenter
                            }
                        }
                    }

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(58)
                        soft: true

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(14)

                            Text {
                                text: "Latest version"
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12)
                                Layout.alignment: Qt.AlignVCenter
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            Text {
                                text: "v" + versionService.latestVersion
                                color: versionService.updateAvailable ? Theme.danger : Theme.success
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(16)
                                font.weight: Font.DemiBold
                                Layout.alignment: Qt.AlignVCenter
                            }
                        }
                    }

                    Item {
                        Layout.fillHeight: true
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        Layout.maximumWidth: Theme.px(500)
                        Layout.alignment: Qt.AlignHCenter
                        columns: Theme.logical(updateCard.width) >= 520 ? 2 : 1
                        columnSpacing: Theme.px(8)
                        rowSpacing: Theme.px(8)

                        GhostButton {
                            Layout.fillWidth: true
                            text: "Check again"
                            iconName: "refresh"
                            onClicked: versionService.checkNow()
                        }

                        PrimaryButton {
                            Layout.fillWidth: true
                            text: versionService.updateAvailable ? "Update available — update now" : "Update from GitHub"
                            iconName: "update"
                            onClicked: confirm.open()
                        }
                    }
                }
            }

            Item {
                Layout.fillHeight: true
            }
        }
    }

    MessageDialog {
        id: confirm
        title: "Update KFPS?"
        text: "KFPS will close, run the existing updater, and relaunch when the update succeeds."
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: updateService.startUpdate()
    }
}
