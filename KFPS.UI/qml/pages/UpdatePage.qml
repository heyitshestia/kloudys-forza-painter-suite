import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Dialogs 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent

    readonly property bool hasUpdate: versionService.updateAvailable
    readonly property string latestLabel: versionService.latestVersion && versionService.latestVersion.length > 0
                                         ? versionService.latestVersion
                                         : "checking"
    readonly property bool headerAlignmentAvailable: Theme.logical(width) >= 900 && updateCard.width > 0
    readonly property bool sideBySide: Theme.logical(updateCard.width) >= 980
    readonly property real headerSourceCenterX: pageColumn.x + updateCard.x + updateCard.width * 0.28
    readonly property real headerPreviewCenterX: pageColumn.x + updateCard.x + updateCard.width * 0.72
    readonly property real headerBannerLeftX: pageColumn.x + updateCard.x
    readonly property real headerBannerRightX: pageColumn.x + updateCard.x + updateCard.width

    FastScrollView {
        id: scroll
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            id: pageColumn
            width: scroll.availableWidth
            height: Math.max(scroll.availableHeight, implicitHeight)
            spacing: Theme.px(18)

            Item {
                Layout.fillHeight: true
            }

            HoverCard {
                id: updateCard
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: Math.max(
                                           Theme.px(440),
                                           Math.min(scroll.availableWidth - Theme.px(40), Theme.px(1180)))
                Layout.minimumWidth: Math.min(scroll.availableWidth - Theme.px(28), Theme.px(380))
                Layout.minimumHeight: Theme.px(root.sideBySide ? 560 : 760)
                strong: true
                padding: Theme.px(24)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(16)

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.px(16)

                        Icon {
                            name: "update"
                            iconSize: Theme.px(58)
                            Layout.alignment: Qt.AlignTop
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(4)

                            Text {
                                Layout.fillWidth: true
                                text: "Update KFPS"
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(30)
                                font.weight: Font.DemiBold
                            }

                            Text {
                                Layout.fillWidth: true
                                text: root.hasUpdate
                                      ? "A newer version is available. Update from here and KFPS will reopen when the updater finishes."
                                      : "KFPS is using the latest version reported by GitHub."
                                color: root.hasUpdate ? Theme.warning : Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(13)
                                wrapMode: Text.Wrap
                                lineHeight: 1.28

                                Behavior on color {
                                    enabled: !Theme.reducedMotion
                                    ColorAnimation { duration: 160 }
                                }
                            }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        columns: root.sideBySide ? 2 : 1
                        columnSpacing: Theme.px(16)
                        rowSpacing: Theme.px(14)

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: root.sideBySide
                            Layout.preferredWidth: root.sideBySide ? Theme.px(650) : -1
                            spacing: Theme.px(14)

                            GlassPanel {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Theme.px(72)
                                soft: true

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: Theme.px(16)
                                    spacing: Theme.px(12)

                                    Rectangle {
                                        Layout.preferredWidth: Theme.px(12)
                                        Layout.preferredHeight: Theme.px(12)
                                        radius: width / 2
                                        color: root.hasUpdate ? Theme.danger : Theme.success
                                        opacity: root.hasUpdate ? (versionService.blinkOn ? 1.0 : 0.36) : 1.0

                                        Behavior on opacity {
                                            enabled: !Theme.reducedMotion
                                            NumberAnimation { duration: 180 }
                                        }
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: root.hasUpdate
                                              ? "Update available: v" + versionService.localVersion + " -> v" + root.latestLabel
                                              : "No update available right now."
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(15)
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }

                                    Text {
                                        text: versionService.checking ? "checking..." : "checked every minute"
                                        color: Theme.muted
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(11)
                                        visible: Theme.logical(updateCard.width) >= 680
                                    }
                                }
                            }

                            GridLayout {
                                Layout.fillWidth: true
                                columns: Theme.logical(updateCard.width) >= 700 ? 2 : 1
                                columnSpacing: Theme.px(14)
                                rowSpacing: Theme.px(14)

                                GlassPanel {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Theme.px(150)
                                    soft: true

                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: Theme.px(18)
                                        spacing: Theme.px(8)

                                        Text {
                                            text: "Current version"
                                            color: Theme.muted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(12)
                                            font.capitalization: Font.AllUppercase
                                            font.letterSpacing: Theme.px(1.2)
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: "v" + versionService.localVersion
                                            color: Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(38)
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: "Installed locally"
                                            color: Theme.muted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(12)
                                            elide: Text.ElideRight
                                        }
                                    }
                                }

                                GlassPanel {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Theme.px(150)
                                    soft: !root.hasUpdate
                                    strong: root.hasUpdate
                                    glow: root.hasUpdate

                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: Theme.px(18)
                                        spacing: Theme.px(8)

                                        Text {
                                            text: root.hasUpdate ? "New version" : "Latest version"
                                            color: root.hasUpdate ? Theme.warning : Theme.muted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(12)
                                            font.capitalization: Font.AllUppercase
                                            font.letterSpacing: Theme.px(1.2)
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: "v" + root.latestLabel
                                            color: root.hasUpdate ? Theme.danger : Theme.success
                                            opacity: root.hasUpdate ? (versionService.blinkOn ? 1.0 : 0.72) : 1.0
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(38)
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight

                                            Behavior on opacity {
                                                enabled: !Theme.reducedMotion
                                                NumberAnimation { duration: 180 }
                                            }
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: root.hasUpdate ? "Ready to install" : "GitHub main matches this install"
                                            color: Theme.muted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(12)
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }

                            PrimaryButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Theme.px(78)
                                text: root.hasUpdate ? "Update to v" + root.latestLabel : "Run Updater"
                                iconName: "update"
                                textPixelSize: Theme.px(18)
                                toolTipText: root.hasUpdate
                                             ? "Download and install the latest KFPS files while preserving personal data."
                                             : "Run the updater to repair or refresh this installation from GitHub."
                                onClicked: confirm.open()
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(12)

                                GhostButton {
                                    Layout.preferredWidth: Theme.px(190)
                                    text: "Check Now"
                                    iconName: "refresh"
                                    toolTipText: "Check GitHub again for a newer KFPS version."
                                    onClicked: versionService.checkNow()
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: "Generated images, editor projects, JSON outputs, Python, dependencies, runtime data, and unlock keys are preserved."
                                    color: Theme.muted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(11.5)
                                    wrapMode: Text.Wrap
                                    lineHeight: 1.25
                                }
                            }
                        }

                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.fillHeight: root.sideBySide
                            Layout.preferredWidth: root.sideBySide ? Theme.px(430) : -1
                            Layout.preferredHeight: Theme.px(root.sideBySide ? 430 : 240)
                            soft: true

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.px(14)
                                spacing: Theme.px(8)

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(10)

                                    Text {
                                        Layout.fillWidth: true
                                        text: "Patch notes"
                                        color: Theme.primaryBright
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(13)
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }

                                    GhostButton {
                                        dense: true
                                        text: "Refresh Notes"
                                        iconName: "refresh"
                                        minimumWidth: Theme.px(84)
                                        toolTipText: "Reload the local patch notes shown here."
                                        onClicked: changelogService.refresh()
                                    }
                                }

                                FastListView {
                                    id: updatePatchNotes
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    clip: true
                                    model: changelogService.model
                                    spacing: Theme.px(7)

                                    delegate: Item {
                                        required property string version
                                        required property string summary
                                        required property string details

                                        width: updatePatchNotes.width
                                        height: Math.max(Theme.px(48), patchNoteContent.implicitHeight + Theme.px(4))

                                        ColumnLayout {
                                            id: patchNoteContent
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.top: parent.top
                                            spacing: Theme.px(3)

                                            RowLayout {
                                                Layout.fillWidth: true
                                                spacing: Theme.px(10)

                                                Text {
                                                    Layout.preferredWidth: Theme.px(68)
                                                    Layout.minimumWidth: Layout.preferredWidth
                                                    text: version
                                                    color: Theme.success
                                                    font.family: Theme.monoFamily
                                                    font.pixelSize: Theme.px(10.2)
                                                    font.weight: Font.DemiBold
                                                    wrapMode: Text.WordWrap
                                                    lineHeight: 1.15
                                                }

                                                Text {
                                                    Layout.fillWidth: true
                                                    text: summary
                                                    color: Theme.text
                                                    font.family: Theme.fontFamily
                                                    font.pixelSize: Theme.px(10.8)
                                                    font.weight: Font.DemiBold
                                                    elide: Text.ElideRight
                                                }
                                            }

                                            Text {
                                                Layout.fillWidth: true
                                                visible: details.length > 0
                                                text: details
                                                color: Theme.muted
                                                font.family: Theme.fontFamily
                                                font.pixelSize: Theme.px(9.8)
                                                wrapMode: Text.WordWrap
                                                lineHeight: 1.15
                                            }
                                        }
                                    }

                                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                                }
                            }
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
        text: "KFPS will close, run the existing updater, and reopen automatically when the update succeeds."
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: updateService.startUpdate()
    }
}
