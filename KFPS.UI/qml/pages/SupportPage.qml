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
    readonly property string donationUrl: "https://ko-fi.com/O7O020EQNQ"
    readonly property var benefits: [
        {
            icon: "transfer",
            title: "Free local tools",
            detail: "Generation, both editors, output management and supported online and offline import/export, including full library transfers, do not require a supporter key. Game and save-format checks still apply."
        },
        {
            icon: "monitor",
            title: "Supporter themes",
            detail: "Windows 94, Patron's Atelier, Carbon Dark and Overdrive 200X remain supporter-only. Public themes and the editor's custom themes stay free."
        },
        {
            icon: "heart",
            title: "Community",
            detail: "Public sharing uses your GitHub sign-in, not a purchase. Community displays the connected server's access rules for protected artwork."
        }
    ]

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
                            text: "Thanks for using KFPS. Optional donations help support its continued development."
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
                    objectName: "DonateToKfps"
                    Layout.fillWidth: !root.wide
                    Layout.preferredWidth: root.wide ? Theme.px(260) : -1
                    Layout.alignment: root.wide ? (Qt.AlignRight | Qt.AlignVCenter) : Qt.AlignHCenter
                    text: "Donate on Ko-fi"
                    iconName: "heart"
                    showArrow: true
                    textPixelSize: Theme.px(13)
                    toolTipText: "Open the official KFPS donation page on Ko-fi."
                    onClicked: desktop.openUrl(root.donationUrl)
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
                            text: "Donations are optional"
                            color: Theme.warning
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(root.compact ? 17 : 21)
                            font.weight: Font.Bold
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "You can use KFPS's local tools without paying or entering a key. A donation is a thank-you, not an access requirement."
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
                text: "KFPS access"
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
                            text: "Theme keys"
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(root.compact ? 15 : 16.5)
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            objectName: "SupporterThemeStatus"
                            text: supporterService.unlocked
                                  ? "Your supporter themes are unlocked. Your existing key and settings are kept."
                                  : "Existing keys still unlock the four supporter themes, without PC binding or online activation. Donations do not issue new keys or unlock Verified Community access."
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
                    text: "Have a theme key? Add or manage it in Settings. No key is needed for the local editing and transfer tools."
                    color: Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(root.compact ? 11.8 : 12.4)
                    wrapMode: Text.WordWrap
                    lineHeight: 1.25
                    lineHeightMode: Text.ProportionalHeight
                }

                GhostButton {
                    objectName: "OpenSupporterKeySettings"
                    Layout.fillWidth: !root.wide
                    Layout.preferredWidth: root.wide ? Theme.px(210) : -1
                    Layout.alignment: root.wide ? Qt.AlignRight : Qt.AlignHCenter
                    text: "Theme Settings"
                    iconName: "settings"
                    toolTipText: "Open Settings to add, replace, or remove an existing theme key."
                    onClicked: appController.navigate("settings")
                }
            }
        }
    }
}
