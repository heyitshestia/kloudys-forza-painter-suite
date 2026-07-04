import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Button {
    id: root

    objectName: "NavButton:" + root.text

    property string iconName: "home"
    property bool active: false
    property bool compact: false
    property bool dense: false

    implicitHeight: Theme.px(compact ? Metrics.compactNavButtonHeight : (dense ? 42 : Metrics.navButtonHeight))
    implicitWidth: Theme.px(compact ? Metrics.compactSidebar - 18 : Metrics.wideSidebar - 20)
    Layout.minimumHeight: root.implicitHeight

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    leftPadding: 0
    rightPadding: 0
    topPadding: 0
    bottomPadding: 0
    scale: down ? 0.985 : 1.0

    transform: Translate {
        id: hoverLift
        y: root.hovered && !root.down ? -Theme.px(1) : 0
        Behavior on y { enabled: !Theme.reducedMotion; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    }
    Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 70; easing.type: Easing.OutCubic } }

    background: Item {
        Rectangle {
            id: activeGlow
            anchors.fill: parent
            anchors.margins: -Theme.px(2)
            radius: Theme.px(11)
            color: "transparent"
            opacity: root.active ? 1 : 0
            layer.enabled: Theme.glassEffects && root.active && !screenshotMode
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Theme.navActiveGlow
                shadowBlur: 0.9
                shadowOpacity: 0.8
                shadowHorizontalOffset: 0
                shadowVerticalOffset: 0
            }
        }

        Rectangle {
            id: chrome
            anchors.fill: parent
            radius: Theme.px(9)
            antialiasing: true
            color: root.active ? "transparent" : (root.hovered ? Theme.navHoverSurface : "transparent")
            border.width: root.active || root.hovered || root.activeFocus ? Theme.px(1) : 0
            border.color: root.activeFocus ? Theme.focusColor : (root.active ? Theme.primaryBright : Theme.borderSoft)
            gradient: root.active ? activeGradient : undefined

            Gradient {
                id: activeGradient
                GradientStop { position: 0.0; color: Theme.navActiveTop }
                GradientStop { position: 0.52; color: Theme.navActiveMiddle }
                GradientStop { position: 1.0; color: Theme.navActiveBottom }
            }

            Behavior on color { ColorAnimation { duration: 120 } }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Math.max(1, Theme.px(1))
            color: Theme.divider
            opacity: root.active ? 0 : 0.34
        }
    }

    contentItem: Loader { sourceComponent: root.compact ? compactContent : wideContent }

    Component {
        id: wideContent
        Item {
            Row {
                anchors.left: parent.left
                anchors.leftMargin: Theme.px(17)
                anchors.right: arrowText.left
                anchors.rightMargin: Theme.px(8)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.px(13)

                Icon {
                    name: root.iconName
                    iconSize: Theme.px(root.dense ? 18 : 20)
                    colorize: root.active
                    tint: Theme.primaryText
                    glow: root.active
                    glowColor: Theme.focusColor
                    iconOpacity: root.active ? 1 : 0.78
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    width: Math.max(0, parent.width - x)
                    text: root.text
                    color: root.active ? Theme.primaryText : Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(root.dense ? 11.5 : 13)
                    font.weight: root.active ? Font.DemiBold : Font.Medium
                    anchors.verticalCenter: parent.verticalCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }

            Text {
                id: arrowText
                width: Theme.px(20)
                text: "›"
                visible: root.active || root.hovered
                color: root.active ? Theme.primaryText : Theme.primaryBright
                opacity: root.active ? 1 : 0.75
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(24)
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                anchors.right: parent.right
                anchors.rightMargin: Theme.px(10)
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    Component {
        id: compactContent
        Column {
            anchors.centerIn: parent
            width: parent.width
            spacing: Theme.px(2)

            Icon {
                name: root.iconName
                iconSize: Theme.px(root.dense ? 17 : 19)
                colorize: root.active
                tint: Theme.primaryText
                glow: root.active
                glowColor: Theme.focusColor
                iconOpacity: root.active ? 1 : 0.78
                anchors.horizontalCenter: parent.horizontalCenter
            }

            Text {
                width: parent.width - Theme.px(8)
                text: root.text
                color: root.active ? Theme.primaryText : Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(root.dense ? 8 : 9)
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }
    }
}
