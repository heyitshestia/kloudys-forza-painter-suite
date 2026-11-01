import QtQuick 6.7
import QtQuick.Window 6.7

Image {
    property string name: "home"
    property bool inverted: false
    source: assetRoot + "/themes/apex-vector/icons/" + name + (inverted ? "-light.svg" : "-dark.svg")
    sourceSize.width: Math.ceil(width * (Window.window ? Window.window.devicePixelRatio : 1))
    sourceSize.height: Math.ceil(height * (Window.window ? Window.window.devicePixelRatio : 1))
    fillMode: Image.PreserveAspectFit
    smooth: true
    // Rasterize the existing vector icon at its display size, without an effect
    // layer. This is also visible in Qt's software-rendering fallback.
}
