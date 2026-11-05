import Foundation
import AVFoundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

/* 用法：vthumb <输入视频> <输出jpg>
   取视频开头一帧（0.1s 处，避免纯黑首帧），长边压到 480，JPEG q68 */
let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: vthumb <in> <out.jpg>\n".data(using: .utf8)!)
    exit(2)
}
let inURL = URL(fileURLWithPath: args[1])
let outURL = URL(fileURLWithPath: args[2])

let asset = AVURLAsset(url: inURL)
let gen = AVAssetImageGenerator(asset: asset)
gen.appliesPreferredTrackTransform = true
gen.maximumSize = CGSize(width: 480, height: 480)
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter = CMTime(seconds: 1, preferredTimescale: 600)
gen.requestedTime = CMTime(seconds: 0.1, preferredTimescale: 600)

do {
    let cg = try gen.copyCGImage(at: gen.requestedTime, actualTime: nil)
    guard let dest = CGImageDestinationCreateWithURL(
        outURL as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else {
        FileHandle.standardError.write("ERR: dest create failed\n".data(using: .utf8)!)
        exit(3)
    }
    CGImageDestinationAddImage(
        dest, cg,
        [kCGImageDestinationLossyCompressionQuality: 0.68] as CFDictionary)
    guard CGImageDestinationFinalize(dest) else {
        FileHandle.standardError.write("ERR: finalize failed\n".data(using: .utf8)!)
        exit(3)
    }
} catch {
    FileHandle.standardError.write("ERR: \(error)\n".data(using: .utf8)!)
    exit(1)
}
