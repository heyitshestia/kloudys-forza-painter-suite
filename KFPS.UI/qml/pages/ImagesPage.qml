import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root

    anchors.fill: parent
    property bool wide: Theme.logical(width) >= 1000
    readonly property bool headerAlignmentAvailable: Boolean(pageLoader.item && pageLoader.item.headerAlignmentAvailable)
    readonly property real headerSourceCenterX: headerAlignmentAvailable ? pageLoader.item.headerSourceCenterX : 0
    readonly property real headerPreviewCenterX: headerAlignmentAvailable ? pageLoader.item.headerPreviewCenterX : 0
    readonly property real headerBannerLeftX: headerAlignmentAvailable ? pageLoader.item.headerBannerLeftX : 0
    readonly property real headerBannerRightX: headerAlignmentAvailable ? pageLoader.item.headerBannerRightX : 0

    Loader {
        id: pageLoader
        anchors.fill: parent
        sourceComponent: root.wide ? wideComponent : compactComponent
    }

    Component {
        id: sourceControls

        ColumnLayout {
            spacing: Theme.px(9)

            SectionHeading {
                Layout.fillWidth: true
                title: "Source image check"
                subtitle: "Inspect the source before committing to a long run."
            }

            PrimaryButton {
                Layout.fillWidth: true
                text: "Choose source image"
                iconName: "images"
                toolTipText: "Choose an image to inspect before starting a long generation."
                onClicked: sourceService.choose()
            }

            GhostButton {
                Layout.fillWidth: true
                text: "Preview Detail Map"
                toolTipText: "Create a preview showing where KFPS detects edges and fine details that may need more shapes."
                enabled: sourceService.path.length > 0
                onClicked: sourceService.buildHeatmap()
            }

            Label {
                text: "Selected file"
            }

            Text {
                Layout.fillWidth: true
                text: sourceService.path || "No source selected"
                color: Theme.subtle
                font.family: Theme.monoFamily
                font.pixelSize: Theme.px(9.5)
                wrapMode: Text.Wrap
                elide: Text.ElideMiddle
                maximumLineCount: 2
            }

            Label {
                text: "Same-aspect target examples"
            }

            Text {
                text: "1 MP   1000 × 1000\n2 MP   1414 × 1414\n4 MP   2000 × 2000\n6 MP   2450 × 2450"
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(11)
                lineHeight: 1.45
            }

            Item {
                Layout.fillHeight: true
            }

            GhostButton {
                Layout.fillWidth: true
                text: "Open Image Tools"
                iconName: "tools"
                toolTipText: "Open background removal, upscaling, and image size tools."
                onClicked: appController.navigate("tools")
            }
        }
    }

    Component {
        id: previewPanel

        ColumnLayout {
            spacing: Theme.px(8)

            RowLayout {
                Layout.fillWidth: true

                Text {
                    text: "SOURCE PREVIEW"
                    color: Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10)
                    font.weight: Font.DemiBold
                }

                Item {
                    Layout.fillWidth: true
                }

                Text {
                    text: sourceService.heatmapUrl ? "Detail heatmap" : "Original source"
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10)
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: Theme.px(220)
                radius: Theme.px(10)
                color: Theme.previewSurfaceSoft
                border.width: Math.max(1, Theme.px(1))
                border.color: Theme.borderSoft

                Image {
                    anchors.fill: parent
                    anchors.margins: Theme.px(12)
                    source: sourceService.heatmapUrl || sourceService.url
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: false
                }

                EmptyState {
                    visible: !(sourceService.heatmapUrl || sourceService.url)
                    anchors.centerIn: parent
                    iconName: "images"
                    title: "Choose an image"
                    message: "The larger source preview appears here."
                }
            }
        }
    }

    Component {
        id: reportPanel

        ColumnLayout {
            spacing: Theme.px(8)

            SectionHeading {
                Layout.fillWidth: true
                title: "Live source report"
                subtitle: "Real measurements from the selected file."
            }

            FastScrollView {
                id: reportScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                Column {
                    width: reportScroll.availableWidth
                    spacing: Theme.px(10)

                    GlassPanel {
                        width: parent.width
                        height: Theme.px(145)
                        soft: true
                        border.width: Math.max(1, Theme.px(2))
                        border.color: sourceService.severity === "red" ? Theme.danger : (sourceService.severity === "yellow" ? Theme.warning : (sourceService.severity === "green" ? Theme.success : Theme.border))

                        Column {
                            anchors.fill: parent
                            anchors.margins: Theme.px(13)
                            spacing: Theme.px(7)

                            Text {
                                text: sourceService.reportTitle
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(13.5)
                                font.weight: Font.DemiBold
                            }

                            Text {
                                width: parent.width
                                text: sourceService.reportMessage
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(10.5)
                                wrapMode: Text.Wrap
                                lineHeight: 1.25
                            }
                        }
                    }

                    GlassPanel {
                        width: parent.width
                        height: Theme.px(158)
                        soft: true

                        Column {
                            anchors.fill: parent
                            anchors.margins: Theme.px(13)
                            spacing: Theme.px(7)

                            Text {
                                text: "Image metrics"
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(13.5)
                                font.weight: Font.DemiBold
                            }

                            Text {
                                width: parent.width
                                text: sourceService.metrics
                                color: Theme.muted
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.px(10)
                                wrapMode: Text.Wrap
                                lineHeight: 1.32
                            }
                        }
                    }

                    GlassPanel {
                        width: parent.width
                        height: Theme.px(125)
                        soft: true

                        Column {
                            anchors.fill: parent
                            anchors.margins: Theme.px(13)
                            spacing: Theme.px(7)

                            Text {
                                text: "Practical guidance"
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(13.5)
                                font.weight: Font.DemiBold
                            }

                            Text {
                                width: parent.width
                                text: "Resize only when the report clearly says the source is too small or unnecessarily large. Transparent PNG is preferred for cutout art."
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(10.5)
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: wideComponent

        GridLayout {
            readonly property bool headerAlignmentAvailable: sourceCard.width > 0 && previewCard.width > 0
            readonly property real headerSourceCenterX: sourceCard.x + sourceCard.width / 2
            readonly property real headerPreviewCenterX: previewCard.x + previewCard.width / 2
            readonly property real headerBannerLeftX: sourceCard.x
            readonly property real headerBannerRightX: previewCard.x + previewCard.width
            columns: 3
            columnSpacing: Theme.px(10)

            HoverCard {
                id: sourceCard
                Layout.preferredWidth: Theme.px(260)
                Layout.minimumWidth: Theme.px(230)
                Layout.fillHeight: true
                padding: Theme.px(16)
                Loader {
                    anchors.fill: parent
                    sourceComponent: sourceControls
                }
            }

            HoverCard {
                id: previewCard
                Layout.fillWidth: true
                Layout.minimumWidth: Theme.px(360)
                Layout.fillHeight: true
                padding: Theme.px(16)
                Loader {
                    anchors.fill: parent
                    sourceComponent: previewPanel
                }
            }

            HoverCard {
                Layout.preferredWidth: Theme.px(320)
                Layout.minimumWidth: Theme.px(280)
                Layout.fillHeight: true
                padding: Theme.px(16)
                Loader {
                    anchors.fill: parent
                    sourceComponent: reportPanel
                }
            }
        }
    }

    Component {
        id: compactComponent

        FastScrollView {
            id: compactScroll
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: compactScroll.availableWidth
                spacing: Theme.px(10)

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(390)
                    padding: Theme.px(16)
                    Loader {
                        anchors.fill: parent
                        sourceComponent: sourceControls
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(430)
                    padding: Theme.px(16)
                    Loader {
                        anchors.fill: parent
                        sourceComponent: previewPanel
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(560)
                    padding: Theme.px(16)
                    Loader {
                        anchors.fill: parent
                        sourceComponent: reportPanel
                    }
                }
            }
        }
    }
}
