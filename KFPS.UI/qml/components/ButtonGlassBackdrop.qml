import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property bool effectEnabled: true
    property real extraOpacity: 1.0

    readonly property var backdropSource: Window.window && Window.window.glassBackdropSource ? Window.window.glassBackdropSource : null
    readonly property point backdropOrigin: backdropSource ? mapToItem(backdropSource, 0, 0) : Qt.point(0, 0)
    readonly property real lensInsetX: Math.max(0, Math.min(width * 0.32, width * Theme.buttonGlassLensInsetX))
    readonly property real lensInsetY: Math.max(0, Math.min(height * 0.36, height * Theme.buttonGlassLensInsetY))
    readonly property real lensWidth: Math.max(2, width - lensInsetX * 2)
    readonly property real lensHeight: Math.max(2, height - lensInsetY * 2)
    readonly property point lensOrigin: Qt.point(
                                            backdropOrigin.x + lensInsetX + width * Theme.buttonGlassLensOffsetX,
                                            backdropOrigin.y + lensInsetY + height * Theme.buttonGlassLensOffsetY)
    readonly property bool backdropActive: root.effectEnabled
                                           && Theme.glassEffects
                                           && Theme.glassBackdropEnabled
                                           && Theme.buttonGlassBackdropOpacity > 0
                                           && backdropSource
                                           && width > 2
                                           && height > 2

    visible: backdropActive

    ShaderEffectSource {
        id: backdropCapture
        visible: false
        sourceItem: root.backdropActive ? root.backdropSource : null
        sourceRect: Qt.rect(root.backdropOrigin.x,
                            root.backdropOrigin.y,
                            root.width,
                            root.height)
        textureSize: Qt.size(Math.max(2, root.width * Theme.buttonGlassBackdropDownsample),
                             Math.max(2, root.height * Theme.buttonGlassBackdropDownsample))
        live: root.backdropActive
        recursive: false
        hideSource: false
        mipmap: true
    }

    MultiEffect {
        anchors.fill: parent
        source: backdropCapture
        blurEnabled: true
        blur: Theme.buttonGlassBackdropBlur
        blurMax: Theme.buttonGlassBackdropBlurMax
        blurMultiplier: Theme.buttonGlassBackdropBlurMultiplier
        brightness: Theme.buttonGlassBackdropBrightness
        contrast: Theme.buttonGlassBackdropContrast
        saturation: Theme.buttonGlassBackdropSaturation
        opacity: Theme.buttonGlassBackdropOpacity * root.extraOpacity
        autoPaddingEnabled: false
    }

    ShaderEffectSource {
        id: lensCapture
        visible: false
        sourceItem: root.backdropActive && Theme.buttonGlassLensOpacity > 0 ? root.backdropSource : null
        sourceRect: Qt.rect(root.lensOrigin.x,
                            root.lensOrigin.y,
                            root.lensWidth,
                            root.lensHeight)
        textureSize: Qt.size(Math.max(2, root.width * Theme.buttonGlassBackdropDownsample),
                             Math.max(2, root.height * Theme.buttonGlassBackdropDownsample))
        live: root.backdropActive
        recursive: false
        hideSource: false
        mipmap: true
    }

    MultiEffect {
        anchors.fill: parent
        visible: root.backdropActive && Theme.buttonGlassLensOpacity > 0
        source: lensCapture
        blurEnabled: Theme.buttonGlassLensBlur > 0
        blur: Theme.buttonGlassLensBlur
        blurMax: Theme.buttonGlassBackdropBlurMax
        blurMultiplier: 0.75
        brightness: Theme.buttonGlassBackdropBrightness + 0.02
        contrast: Theme.buttonGlassLensContrast
        saturation: Theme.buttonGlassLensSaturation
        opacity: Theme.buttonGlassLensOpacity * root.extraOpacity
        autoPaddingEnabled: false
    }

    Rectangle {
        anchors.fill: parent
        visible: root.backdropActive && Theme.buttonGlassLensOpacity > 0
        color: "transparent"
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Theme.buttonGlassLensLeftHighlight }
            GradientStop { position: 0.18; color: "#00ffffff" }
            GradientStop { position: 0.50; color: Theme.buttonGlassLensCenterHighlight }
            GradientStop { position: 0.82; color: "#00ffffff" }
            GradientStop { position: 1.0; color: Theme.buttonGlassLensRightShadow }
        }
        opacity: 0.42 * root.extraOpacity
    }

}
