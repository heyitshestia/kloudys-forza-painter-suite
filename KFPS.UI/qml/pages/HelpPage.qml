import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent
    property bool wide: Theme.logical(width) >= 1020
    property bool medium: Theme.logical(width) >= 760
    readonly property bool headerAlignmentAvailable: Boolean(pageLoader.item && pageLoader.item.headerAlignmentAvailable)
    readonly property real headerSourceCenterX: headerAlignmentAvailable ? pageLoader.item.headerSourceCenterX : 0
    readonly property real headerPreviewCenterX: headerAlignmentAvailable ? pageLoader.item.headerPreviewCenterX : 0
    readonly property real headerBannerLeftX: headerAlignmentAvailable ? pageLoader.item.headerBannerLeftX : 0
    readonly property real headerBannerRightX: headerAlignmentAvailable ? pageLoader.item.headerBannerRightX : 0

    Component.onCompleted: helpService.setCategory("all")

    Loader {
        id: pageLoader
        anchors.fill: parent
        sourceComponent: root.wide ? wideComponent : compactComponent
    }

    Component {
        id: searchAndCategories
        ColumnLayout {
            spacing: Theme.px(10)

            SectionHeading {
                Layout.fillWidth: true
                title: "Help Center"
                subtitle: helpService.resultSummary
            }

            KfpsTextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: "Search: template, import, editor..."
                toolTipText: "Search all help topics in plain language. Empty the box to show every topic again."
                onTextChanged: helpService.search(text)
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(7)
                PrimaryButton {
                    Layout.fillWidth: true
                    dense: true
                    iconName: "check"
                    text: "Start Here"
                    toolTipText: "Open the beginner guide from choosing an image through saving the result in Forza."
                    onClicked: helpService.selectTopic("first-run")
                }
                PrimaryButton {
                    Layout.fillWidth: true
                    dense: true
                    iconName: "transfer"
                    text: "FH6 Template"
                    toolTipText: "Open the exact one-time steps for making a reusable FH6 import template."
                    onClicked: helpService.selectTopic("fh6-template")
                }
            }

            GhostButton {
                Layout.fillWidth: true
                dense: true
                iconName: "changelog"
                text: "Copy Support Info"
                toolTipText: "Copy a short list of useful details to include when asking for help."
                onClicked: helpService.copySupportChecklist()
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(7)
                GhostButton {
                    Layout.fillWidth: true
                    dense: true
                    iconName: "help"
                    text: "Fix a Problem"
                    toolTipText: "Open the troubleshooting and support guide."
                    onClicked: helpService.selectTopic("support-checklist")
                }
            }

            Label {
                Layout.fillWidth: true
                text: "Categories"
            }

            FastListView {
                id: categoryList
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: helpService.categoryModel
                clip: true
                spacing: Theme.px(6)
                currentIndex: 0

                delegate: Button {
                    id: categoryButton
                    objectName: "HelpCategory:" + categoryButton.title
                    required property int index
                    required property string key
                    required property string title
                    required property string summary
                    required property int count

                    width: categoryList.width
                    height: Theme.px(54)
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    scale: Theme.classicMode ? 1.0 : (down ? 0.985 : 1.0)
                    Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 75; easing.type: Easing.OutCubic } }
                    onClicked: {
                        categoryList.currentIndex = index;
                        helpService.setCategory(key);
                    }

                    KfpsToolTip {
                        visible: categoryButton.hovered
                        text: categoryButton.summary
                    }

                    background: Rectangle {
                        radius: Theme.framedRadius(Theme.px(12))
                        color: Theme.angularControlsEnabled
                               ? "transparent"
                               : (categoryButton.index === categoryList.currentIndex
                               ? (categoryButton.hovered ? Theme.primaryDeep : Theme.helpCategorySelected)
                               : (categoryButton.hovered ? Theme.helpCategoryHover : Theme.helpCategorySurface))
                        border.width: Theme.classicMode
                                      ? 0
                                      : (Theme.angularControlsEnabled
                                      ? 0
                                      : (categoryButton.activeFocus
                                      ? Theme.px(2)
                                      : (Theme.customFrameExclusive
                                         ? 0
                                         : Math.max(1, Theme.px(categoryButton.index === categoryList.currentIndex ? 2 : 1)))))
                        border.color: categoryButton.activeFocus
                                      ? Theme.focusColor
                                      : (categoryButton.index === categoryList.currentIndex
                                         ? Theme.primaryBright
                                         : (categoryButton.hovered ? Theme.primary : Theme.borderSoft))
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Behavior on border.color { ColorAnimation { duration: 120 } }

                        AngularControlFrame {
                            anchors.fill: parent
                            fillColor: categoryButton.index === categoryList.currentIndex
                                       ? (categoryButton.hovered ? Theme.primaryBright : Theme.helpCategorySelected)
                                       : (categoryButton.hovered ? Theme.helpCategoryHover : Theme.helpCategorySurface)
                            borderColor: categoryButton.activeFocus
                                         ? Theme.focusColor
                                         : (categoryButton.index === categoryList.currentIndex
                                            ? Theme.signalSecondary
                                            : (categoryButton.hovered ? Theme.primary : Theme.borderSoft))
                            accentColor: Theme.signalSecondary
                            hovered: categoryButton.hovered
                            pressed: categoryButton.down
                            selected: categoryButton.index === categoryList.currentIndex
                            focused: categoryButton.activeFocus
                            panelFrame: Theme.floatingPanelsEnabled
                                        && categoryButton.index !== categoryList.currentIndex
                            decorationVisible: categoryButton.index === categoryList.currentIndex
                                               || categoryButton.hovered
                                               || categoryButton.activeFocus
                        }

                        ClassicBevel {
                            anchors.fill: parent
                            pressed: categoryButton.down || categoryButton.index === categoryList.currentIndex
                        }

                        ClassicFocusRect {
                            anchors.fill: parent
                            anchors.margins: Theme.px(4)
                            active: categoryButton.activeFocus && categoryButton.index !== categoryList.currentIndex
                        }
                    }

                    contentItem: RowLayout {
                        spacing: Theme.px(9)
                        Text {
                            Layout.fillWidth: true
                            text: categoryButton.title
                            color: categoryButton.index === categoryList.currentIndex
                                   ? Theme.primaryText
                                   : (Theme.technicalTypographyEnabled ? Theme.signalSecondary : Theme.text)
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(13)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Rectangle {
                            Layout.preferredWidth: Theme.px(34)
                            Layout.preferredHeight: Theme.px(24)
                            radius: Theme.corner(height / 2)
                            color: categoryButton.index === categoryList.currentIndex ? Theme.helpBadgeSelected : Theme.helpBadge
                            border.width: Math.max(1, Theme.px(1))
                            border.color: Theme.helpBadgeBorder
                            Text {
                                anchors.centerIn: parent
                                text: categoryButton.count
                                color: categoryButton.index === categoryList.currentIndex ? Theme.primaryText : Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(11.5)
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: topicBrowser
        ColumnLayout {
            spacing: Theme.px(10)

            SectionHeading {
                Layout.fillWidth: true
                title: "Topics"
                subtitle: "Pick a guide, then follow the right pane."
            }

            FastListView {
                id: topicList
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: helpService.topicModel
                clip: true
                spacing: Theme.px(7)
                currentIndex: 0

                delegate: Button {
                    id: topicButton
                    objectName: "HelpTopic:" + topicButton.title
                    required property int index
                    required property string title
                    required property string summary
                    required property string category
                    required property string match

                    width: topicList.width
                    height: Theme.px(86)
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    scale: Theme.classicMode ? 1.0 : (down ? 0.985 : 1.0)
                    Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 75; easing.type: Easing.OutCubic } }
                    onClicked: {
                        topicList.currentIndex = index;
                        helpService.select(index);
                    }

                    KfpsToolTip {
                        visible: topicButton.hovered
                        text: topicButton.summary
                    }

                    background: Rectangle {
                        radius: Theme.framedRadius(Theme.px(13))
                        color: Theme.angularControlsEnabled
                               ? "transparent"
                               : (topicButton.index === topicList.currentIndex
                               ? (topicButton.hovered ? Theme.primaryDeep : Theme.helpTopicSelected)
                               : (topicButton.hovered ? Theme.helpTopicHover : Theme.helpTopicSurface))
                        border.width: Theme.classicMode
                                      ? 0
                                      : (Theme.angularControlsEnabled
                                      ? 0
                                      : (topicButton.activeFocus
                                      ? Theme.px(2)
                                      : (Theme.customFrameExclusive
                                         ? 0
                                         : Math.max(1, Theme.px(topicButton.index === topicList.currentIndex ? 2 : 1)))))
                        border.color: topicButton.activeFocus
                                      ? Theme.focusColor
                                      : (topicButton.index === topicList.currentIndex
                                         ? Theme.primaryBright
                                         : (topicButton.hovered ? Theme.primary : Theme.borderSoft))
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Behavior on border.color { ColorAnimation { duration: 120 } }

                        AngularControlFrame {
                            anchors.fill: parent
                            fillColor: topicButton.index === topicList.currentIndex
                                       ? (topicButton.hovered ? Theme.primaryBright : Theme.helpTopicSelected)
                                       : (topicButton.hovered ? Theme.helpTopicHover : Theme.helpTopicSurface)
                            borderColor: topicButton.activeFocus
                                         ? Theme.focusColor
                                         : (topicButton.index === topicList.currentIndex
                                            ? (topicButton.hovered ? Theme.primaryBright : Theme.signalSecondary)
                                            : (topicButton.hovered ? Theme.primary : Theme.borderSoft))
                            accentColor: Theme.signalSecondary
                            hovered: topicButton.hovered
                            pressed: topicButton.down
                            selected: topicButton.index === topicList.currentIndex
                            focused: topicButton.activeFocus
                            panelFrame: true
                            decorationVisible: topicButton.index === topicList.currentIndex
                                               || topicButton.hovered
                                               || topicButton.activeFocus
                        }

                        ClassicBevel {
                            anchors.fill: parent
                            pressed: topicButton.down || topicButton.index === topicList.currentIndex
                        }

                        ClassicFocusRect {
                            anchors.fill: parent
                            anchors.margins: Theme.px(4)
                            active: topicButton.activeFocus && topicButton.index !== topicList.currentIndex
                        }
                    }

                    contentItem: Column {
                        spacing: Theme.px(3)
                        anchors.margins: Theme.px(10)
                        Text {
                            width: parent.width
                            text: topicButton.title
                            color: Theme.floatingPanelsEnabled
                                   ? (topicButton.index === topicList.currentIndex ? Theme.signalPrimary : Theme.text)
                                   : (topicButton.index === topicList.currentIndex ? Theme.primaryText : Theme.text)
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(13.4)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            text: topicButton.summary
                            color: Theme.floatingPanelsEnabled
                                   ? (topicButton.index === topicList.currentIndex ? Theme.signalSecondary : Theme.muted)
                                   : (topicButton.index === topicList.currentIndex ? Theme.primaryText : Theme.muted)
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.6)
                            lineHeight: 1.12
                            maximumLineCount: 2
                            wrapMode: Text.Wrap
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            text: topicButton.match
                            color: Theme.subtle
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10.4)
                            font.capitalization: Font.AllUppercase
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            EmptyState {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.px(140)
                visible: !helpService.hasResults
                title: "No help topic found"
                message: "Try fewer words or clear the selected category."
            }
        }
    }

    Component {
        id: articleView
        ColumnLayout {
            spacing: Theme.px(12)

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(10)

                SectionHeading {
                    Layout.fillWidth: true
                    title: helpService.title
                    subtitle: helpService.breadcrumb
                }

                GhostButton {
                    dense: true
                    iconName: "changelog"
                    text: "Copy Support Info"
                    visible: Theme.logical(root.width) >= 930
                    toolTipText: "Copy a short list of useful details to include when asking for help."
                    onClicked: helpService.copySupportChecklist()
                }
            }

            Text {
                Layout.fillWidth: true
                text: helpService.summary
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(13.6)
                wrapMode: Text.Wrap
                lineHeight: 1.28
            }

            Rectangle {
                Layout.fillWidth: true
                height: Math.max(1, Theme.px(1))
                color: Theme.borderSoft
            }

            FastScrollView {
                id: articleScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                Column {
                    id: articleColumn
                    width: articleScroll.availableWidth
                    spacing: Theme.px(12)

                    GlassPanel {
                        width: articleColumn.width
                        height: stepsColumn.implicitHeight + Theme.px(28)
                        strong: true
                        glow: true
                        visible: helpService.steps.length > 0

                        Column {
                            id: stepsColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.px(14)
                            spacing: Theme.px(8)

                            RowLayout {
                                width: parent.width
                                spacing: Theme.px(8)
                                Icon {
                                    name: "check"
                                    iconSize: Theme.px(18)
                                    colorize: true
                                    tint: Theme.primaryBright
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: "Do This"
                                    color: Theme.primaryBright
                                    font.family: Theme.displayFamily
                                    font.pixelSize: Theme.px(16.5)
                                    font.weight: Font.DemiBold
                                }
                            }

                            Repeater {
                                model: helpService.steps
                                delegate: RowLayout {
                                    required property int index
                                    required property string modelData
                                    width: stepsColumn.width
                                    spacing: Theme.px(10)
                                    Rectangle {
                                        Layout.preferredWidth: Theme.px(29)
                                        Layout.preferredHeight: Theme.px(29)
                                        radius: Theme.corner(height / 2)
                                        color: Theme.stepBadge
                                        border.width: Math.max(1, Theme.px(1))
                                        border.color: Theme.primaryBright
                                        Text {
                                            anchors.centerIn: parent
                                            text: index + 1
                                            color: "white"
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(12)
                                            font.weight: Font.Bold
                                        }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(13.2)
                                        wrapMode: Text.Wrap
                                        lineHeight: 1.28
                                    }
                                }
                            }
                        }
                    }

                    Repeater {
                        model: helpService.sections
                        delegate: GlassPanel {
                            required property var modelData
                            width: articleColumn.width
                            height: sectionContent.implicitHeight + Theme.px(28)
                            strong: true

                            Column {
                                id: sectionContent
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: Theme.px(14)
                                spacing: Theme.px(7)
                                Text {
                                    width: parent.width
                                    text: modelData.heading
                                    color: Theme.primaryBright
                                    font.family: Theme.displayFamily
                                    font.pixelSize: Theme.px(15.4)
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.Wrap
                                }
                                Text {
                                    width: parent.width
                                    text: modelData.body
                                    color: Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(13)
                                    wrapMode: Text.Wrap
                                    lineHeight: 1.38
                                }
                            }
                        }
                    }

                    GlassPanel {
                        width: articleColumn.width
                        height: pitfallsColumn.implicitHeight + Theme.px(28)
                        strong: true
                        visible: helpService.pitfalls.length > 0

                        Column {
                            id: pitfallsColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.px(14)
                            spacing: Theme.px(8)
                            Text {
                                width: parent.width
                                text: "Avoid This"
                                color: Theme.warning
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(15.4)
                                font.weight: Font.DemiBold
                            }
                            Repeater {
                                model: helpService.pitfalls
                                delegate: RowLayout {
                                    required property string modelData
                                    width: pitfallsColumn.width
                                    spacing: Theme.px(8)
                                    Text {
                                        Layout.preferredWidth: Theme.px(16)
                                        text: "!"
                                        color: Theme.warning
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(13)
                                        font.weight: Font.Bold
                                        horizontalAlignment: Text.AlignHCenter
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(12.8)
                                        wrapMode: Text.Wrap
                                        lineHeight: 1.28
                                    }
                                }
                            }
                        }
                    }

                    GlassPanel {
                        width: articleColumn.width
                        height: relatedColumn.implicitHeight + Theme.px(28)
                        strong: true
                        visible: helpService.relatedTopics.length > 0

                        Column {
                            id: relatedColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.px(14)
                            spacing: Theme.px(8)
                            Text {
                                width: parent.width
                                text: "Related"
                                color: Theme.primaryBright
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(15.4)
                                font.weight: Font.DemiBold
                            }
                            Flow {
                                width: parent.width
                                spacing: Theme.px(7)
                                Repeater {
                                    model: helpService.relatedTopics
                                    delegate: GhostButton {
                                        required property var modelData
                                        dense: true
                                        text: modelData.title
                                        showArrow: true
                                        toolTipText: "Open the related guide: " + modelData.title
                                        onClicked: helpService.selectTopic(modelData.key)
                                    }
                                }
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
            readonly property bool headerAlignmentAvailable: searchCard.width > 0 && articleCard.width > 0
            readonly property real headerSourceCenterX: searchCard.x + searchCard.width / 2
            readonly property real headerPreviewCenterX: articleCard.x + articleCard.width / 2
            readonly property real headerBannerLeftX: searchCard.x
            readonly property real headerBannerRightX: articleCard.x + articleCard.width
            columns: 3
            columnSpacing: Theme.px(10)

            HoverCard {
                id: searchCard
                Layout.preferredWidth: Theme.px(292)
                Layout.fillHeight: true
                padding: Theme.px(15)
                Loader { anchors.fill: parent; sourceComponent: searchAndCategories }
            }

            HoverCard {
                Layout.preferredWidth: Theme.px(365)
                Layout.fillHeight: true
                padding: Theme.px(15)
                Loader { anchors.fill: parent; sourceComponent: topicBrowser }
            }

            HoverCard {
                id: articleCard
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: Theme.px(18)
                Loader { anchors.fill: parent; sourceComponent: articleView }
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
                    Layout.preferredHeight: root.medium ? Theme.px(315) : Theme.px(380)
                    padding: Theme.px(15)
                    Loader { anchors.fill: parent; sourceComponent: searchAndCategories }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(380)
                    padding: Theme.px(15)
                    Loader { anchors.fill: parent; sourceComponent: topicBrowser }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(720)
                    padding: Theme.px(16)
                    Loader { anchors.fill: parent; sourceComponent: articleView }
                }
            }
        }
    }
}
