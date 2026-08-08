import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root

    objectName: "SupportPage"
    anchors.fill: parent
    readonly property bool wide: Theme.logical(width) >= 980
    readonly property bool compact: Theme.logical(width) < 720
    readonly property string supporterUrl: "https://ko-fi.com/s/2d1507698d"
    readonly property var benefits: [
        {
            icon: "transfer",
            title: "Instant Offline Imports & Exports",
            detail: "Export complete FH4, FH5, FH6, and FM8 vinyl libraries into KFPS in one action, then import compatible JSON directly into supported FH4, FH6, or FM8 save data. No game needs to be started."
        },
        {
            icon: "monitor",
            title: "Four Extra Themes",
            detail: "Make KFPS your own with Windows 94, Patron's Atelier, Carbon Dark, and Overdrive 200X, all included alongside every public theme."
        },
        {
            icon: "heart",
            title: "Supporter Community",
            detail: "Browse and download supporter-only vinyls, publish your own work to the supporter catalog, and unlock supporter designs featured for the whole Community to see."
        }
    ]

    Component.onCompleted: {
        if (supporterService.unlocked)
            Qt.callLater(function () { appController.navigate("create") })
    }

    Connections {
        target: supporterService

        function onChanged() {
            if (supporterService.unlocked)
                appController.navigate("create")
        }
    }

    FastScrollView {
        id: scroll

        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            spacing: Theme.px(16)

            GridLayout {
                Layout.fillWidth: true
                columns: root.wide ? 2 : 1
                columnSpacing: Theme.px(24)
                rowSpacing: Theme.px(14)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(14)

                    Rectangle {
                        Layout.preferredWidth: Theme.px(root.compact ? 48 : 62)
                        Layout.preferredHeight: Layout.preferredWidth
                        radius: Theme.corner(width / 2)
                        color: Theme.angularControlsEnabled ? "transparent" : Theme.logoCapsuleSurface
                        border.width: Theme.angularControlsEnabled ? 0 : Math.max(1, Theme.px(1))
                        border.color: Theme.primaryBright

                        AngularControlFrame {
                            anchors.fill: parent
                            fillColor: Theme.logoCapsuleSurface
                            borderColor: Theme.primaryBright
                            accentColor: Theme.signalSecondary
                            selected: true
                        }

                        Icon {
                            anchors.centerIn: parent
                            name: "heart"
                            iconSize: Theme.px(root.compact ? 24 : 32)
                            glow: true
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.px(5)

                        Text {
                            Layout.fillWidth: true
                            text: "Support KFPS"
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(root.compact ? 22 : 27)
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Keep every core KFPS workflow free while unlocking full offline library tools, supporter vinyl sharing, and four custom themes with one purchase."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(root.compact ? 12.8 : 14.2)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.28
                            lineHeightMode: Text.ProportionalHeight
                        }
                    }
                }

                PrimaryButton {
                    Layout.fillWidth: !root.wide
                    Layout.preferredWidth: root.wide ? Theme.px(260) : -1
                    Layout.alignment: root.wide ? (Qt.AlignRight | Qt.AlignVCenter) : Qt.AlignHCenter
                    text: "Get a Supporter Key"
                    iconName: "heart"
                    showArrow: true
                    textPixelSize: Theme.px(13)
                    toolTipText: "Open the official KFPS supporter-key product page on Ko-fi."
                    onClicked: desktop.openUrl(root.supporterUrl)
                }
            }

            HoverCard {
                Layout.fillWidth: true
                Layout.preferredHeight: purchaseContent.implicitHeight + Theme.px(34)
                strong: true
                padding: Theme.px(17)

                RowLayout {
                    id: purchaseContent

                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    spacing: Theme.px(14)

                    Icon {
                        name: "check"
                        iconSize: Theme.px(30)
                        tint: Theme.warning
                        glowColor: Theme.warning
                        glow: true
                        Layout.alignment: Qt.AlignTop
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.px(4)

                        Text {
                            Layout.fillWidth: true
                            text: "ONE-TIME PURCHASE - NOT A SUBSCRIPTION"
                            color: Theme.warning
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(root.compact ? 17 : 21)
                            font.weight: Font.Bold
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "You pay once for the supporter key. There is no monthly fee and no recurring KFPS charge."
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(root.compact ? 13 : 14)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.28
                            lineHeightMode: Text.ProportionalHeight
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: "What the supporter key unlocks"
                color: Theme.primaryBright
                font.family: Theme.displayFamily
                font.pixelSize: Theme.px(root.compact ? 19 : 22)
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }

            GridLayout {
                Layout.fillWidth: true
                columns: root.wide ? 3 : 1
                columnSpacing: Theme.px(12)
                rowSpacing: Theme.px(12)

                Repeater {
                    model: root.benefits

                    delegate: HoverCard {
                        required property var modelData

                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(root.wide ? 246 : 194)
                        padding: Theme.px(19)
                        soft: true

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: Theme.px(9)

                            Icon {
                                name: modelData.icon
                                iconSize: Theme.px(40)
                                glow: true
                                Layout.alignment: Qt.AlignLeft
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData.title
                                color: Theme.primaryBright
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(root.compact ? 17 : 18.5)
                                font.weight: Font.DemiBold
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                text: modelData.detail
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(root.compact ? 12.5 : 13.2)
                                wrapMode: Text.WordWrap
                                lineHeight: 1.28
                                lineHeightMode: Text.ProportionalHeight
                            }
                        }
                    }
                }
            }

            GlassPanel {
                Layout.fillWidth: true
                Layout.preferredHeight: freeContent.implicitHeight + Theme.px(30)
                soft: true

                RowLayout {
                    id: freeContent

                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.px(15)
                    spacing: Theme.px(12)

                    Icon {
                        name: "transfer"
                        iconSize: Theme.px(28)
                        Layout.alignment: Qt.AlignTop
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.px(4)

                        Text {
                            Layout.fillWidth: true
                            text: "What stays available without a key"
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(root.compact ? 15 : 16.5)
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Generation, the manual editor, output management, the public Community catalog, and online live import/export for FH4, FH5, FH6, and FM8 remain available without supporter access."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(root.compact ? 12 : 12.8)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.28
                            lineHeightMode: Text.ProportionalHeight
                        }
                    }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: root.wide ? 2 : 1
                columnSpacing: Theme.px(14)
                rowSpacing: Theme.px(10)

                Text {
                    Layout.fillWidth: true
                    text: "Already purchased? Add the key from Settings. KFPS verifies and registers a valid key automatically."
                    color: Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(root.compact ? 11.8 : 12.4)
                    wrapMode: Text.WordWrap
                    lineHeight: 1.25
                    lineHeightMode: Text.ProportionalHeight
                }

                GhostButton {
                    Layout.fillWidth: !root.wide
                    Layout.preferredWidth: root.wide ? Theme.px(210) : -1
                    Layout.alignment: root.wide ? Qt.AlignRight : Qt.AlignHCenter
                    text: "Open Key Settings"
                    iconName: "settings"
                    toolTipText: "Open Settings to add, replace, repair, or release a supporter key."
                    onClicked: appController.navigate("settings")
                }
            }
        }
    }
}
