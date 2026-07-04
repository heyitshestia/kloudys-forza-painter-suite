import QtQuick 6.7
import QtQuick.Controls 6.7
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
            spacing: Theme.px(16)

            SectionHeading {
                Layout.fillWidth: true
                title: "Source preparation tools"
                subtitle: "These helpers open externally. Use them before generation when a source needs a clean cutout, a better size, or lighter compression."
            }

            GridLayout {
                Layout.fillWidth: true
                columns: Theme.logical(root.width) > 900 ? 3 : 1
                columnSpacing: Theme.px(12)
                rowSpacing: Theme.px(12)

                WorkflowCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(250)
                    number: ""
                    title: "Background Remover"
                    description: "Cut out opaque backgrounds so the generator spends shapes on the vinyl instead of the backdrop."
                    iconName: "cutout"
                    buttonText: "Open PhotoRoom"
                    onAction: desktop.openUrl("https://www.photoroom.com/tools/background-remover")
                }

                WorkflowCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(250)
                    number: ""
                    title: "Browser Upscaler"
                    description: "Upscale genuinely small art before using a detail-heavy preset. Best for tiny logos and low-resolution references."
                    iconName: "upscale"
                    buttonText: "Open Upscaler"
                    onAction: desktop.openUrl("https://hcodx.com/tools/image-upscaler")
                }

                WorkflowCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(250)
                    number: ""
                    title: "Resize / Compress"
                    description: "Bring oversized art into a practical megapixel range and export clean PNG or WebP inputs."
                    iconName: "compress"
                    buttonText: "Open Squoosh"
                    onAction: desktop.openUrl("https://squoosh.app")
                }
            }

            HoverCard {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.px(160)
                padding: Theme.px(18)

                Column {
                    anchors.fill: parent
                    spacing: Theme.px(10)

                    Text {
                        text: "Nothing is uploaded by KFPS"
                        color: Theme.primaryBright
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(16)
                        font.weight: Font.DemiBold
                    }

                    Text {
                        width: parent.width
                        text: "KFPS only opens these tools. Read each service's privacy terms before uploading personal or unpublished artwork. The local browser upscaler remains on your machine when available."
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(12)
                        wrapMode: Text.Wrap
                        lineHeight: 1.3
                    }
                }
            }
        }
    }
}
