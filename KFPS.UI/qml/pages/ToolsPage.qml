import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent
    readonly property bool headerAlignmentAvailable: Theme.logical(width) > 900
                                                     && removeBackgroundCard.width > 0
                                                     && compressCard.width > 0
    readonly property real headerSourceCenterX: workflowGrid.x + removeBackgroundCard.x + removeBackgroundCard.width / 2
    readonly property real headerPreviewCenterX: workflowGrid.x + compressCard.x + compressCard.width / 2
    readonly property real headerBannerLeftX: workflowGrid.x + removeBackgroundCard.x
    readonly property real headerBannerRightX: workflowGrid.x + compressCard.x + compressCard.width

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
                title: "Tools"
                subtitle: "Quick source-prep shortcuts for cleaner cutouts, better source size, and lighter image files before generation."
            }

            GridLayout {
                id: workflowGrid
                Layout.fillWidth: true
                columns: Theme.logical(root.width) > 900 ? 3 : 1
                columnSpacing: Theme.px(12)
                rowSpacing: Theme.px(12)

                WorkflowCard {
                    id: removeBackgroundCard
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(250)
                    number: ""
                    title: "Remove background"
                    description: "Use this when an image still has a solid or messy background. Cleaner transparency usually means fewer wasted shapes."
                    iconName: "cutout"
                    buttonText: "Open PhotoRoom"
                    onAction: desktop.openUrl("https://www.photoroom.com/tools/background-remover")
                }

                WorkflowCard {
                    id: compressCard
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(250)
                    number: ""
                    title: "Upscale small sources"
                    description: "Use this for tiny logos or low-resolution references before running detailed presets. Do not upscale already large images."
                    iconName: "upscale"
                    buttonText: "Open Upscaler"
                    onAction: desktop.openUrl("https://hcodx.com/tools/image-upscaler")
                }

                WorkflowCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(250)
                    number: ""
                    title: "Resize or compress"
                    description: "Use this when a source is much too large, saved in an awkward format, or needs a cleaner PNG/WebP export."
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
                        text: "Privacy reminder"
                        color: Theme.primaryBright
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(16)
                        font.weight: Font.DemiBold
                    }

                    Text {
                        width: parent.width
                        text: "KFPS only opens these websites in your browser. Check each site's privacy policy and terms before uploading personal, paid, unreleased, or client artwork."
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
