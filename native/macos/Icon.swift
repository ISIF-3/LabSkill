import AppKit

func color(_ hex: UInt32, alpha: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((hex >> 16) & 255) / 255,
            green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: alpha)
}

func drawIcon(size: Int, path: String) throws {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
                                 bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                 isPlanar: false, colorSpaceName: .deviceRGB,
                                 bytesPerRow: 0, bitsPerPixel: 0)!
    let context = NSGraphicsContext(bitmapImageRep: bitmap)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    let scale = CGFloat(size) / 1024
    context.cgContext.scaleBy(x: scale, y: scale)

    let tile = NSBezierPath(roundedRect: NSRect(x: 70, y: 76, width: 884, height: 884),
                            xRadius: 194, yRadius: 194)
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowColor = color(0x00040C, alpha: 0.28)
    shadow.shadowBlurRadius = 23
    shadow.shadowOffset = NSSize(width: 0, height: -13)
    shadow.set()
    color(0x102132).setFill()
    tile.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(starting: color(0x101B29), ending: color(0x24445D))!.draw(in: tile, angle: 72)
    color(0xA7D9FA, alpha: 0.17).setStroke()
    tile.lineWidth = 3
    tile.stroke()

    for (x, y, opacity) in [(522.0, 624.0, 0.25), (552.0, 584.0, 0.45), (582.0, 544.0, 0.8)] {
        let card = NSBezierPath(roundedRect: NSRect(x: x, y: y, width: 176, height: 112),
                                xRadius: 20, yRadius: 20)
        color(0x25465E).setFill()
        card.fill()
        color(0x86D0FF, alpha: opacity).setStroke()
        card.lineWidth = 5
        card.stroke()
        let line = NSBezierPath()
        line.move(to: NSPoint(x: x + 28, y: y + 54))
        line.line(to: NSPoint(x: x + 109, y: y + 54))
        line.lineWidth = 7
        line.lineCapStyle = .round
        line.stroke()
    }

    let mark = NSBezierPath()
    mark.move(to: NSPoint(x: 290, y: 752))
    mark.line(to: NSPoint(x: 421, y: 752))
    mark.line(to: NSPoint(x: 421, y: 416))
    mark.line(to: NSPoint(x: 749, y: 416))
    mark.line(to: NSPoint(x: 749, y: 282))
    mark.line(to: NSPoint(x: 290, y: 282))
    mark.close()
    NSGradient(starting: color(0x349CEC), ending: color(0x9AE4FF))!.draw(in: mark, angle: 90)
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: path))
}

let folder = CommandLine.arguments[1]
for (name, size) in [("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
                     ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
                     ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
                     ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
                     ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024)] {
    try drawIcon(size: size, path: folder + "/" + name)
}
