import SwiftUI

enum BoardStyle {
    static let blue = Color(red: 0.32, green: 0.75, blue: 0.96)
    static let peach = Color(red: 0.91, green: 0.61, blue: 0.48)
    static let muted = Color.white.opacity(0.53)
    static let background = LinearGradient(colors: [Color(red: 0.19, green: 0.20, blue: 0.18),
                                                     Color(red: 0.10, green: 0.11, blue: 0.10)],
                                          startPoint: .topLeading, endPoint: .bottomTrailing)
}

struct UsageCard: View {
    let snapshot: UsageSnapshot
    var date = Date()
    var syncFailed = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            ProviderColumn(provider: snapshot.codex, date: date, syncFailed: syncFailed)
            Rectangle().fill(.white.opacity(0.09)).frame(width: 0.5)
            ProviderColumn(provider: snapshot.claude, date: date, syncFailed: syncFailed)
        }
        .foregroundStyle(.white)
        .fontDesign(.rounded)
        .padding(12)
        .background(BoardStyle.background)
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).strokeBorder(.white.opacity(0.13), lineWidth: 0.7))
    }
}

private struct ProviderColumn: View {
    let provider: ProviderUsage
    let date: Date
    let syncFailed: Bool
    private var isCodex: Bool { provider.id == "codex" }
    private var tint: Color { isCodex ? BoardStyle.blue : BoardStyle.peach }
    private var stale: Bool { syncFailed || provider.isStale(at: date) }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                if isCodex {
                    Image(systemName: "command").font(.system(size: 17, weight: .medium))
                } else {
                    ClaudeMark().fill(BoardStyle.peach).frame(width: 19, height: 19)
                }
                Text(provider.name).font(.system(size: 16, weight: .semibold))
                Spacer(minLength: 1)
                Text("残り").font(.system(size: 9)).foregroundStyle(BoardStyle.muted)
            }

            HStack(alignment: .top, spacing: 10) {
                QuotaCell(window: provider.window("session"), label: "5時間", tint: tint, date: date)
                QuotaCell(window: provider.window("weekly"), label: "週間", tint: tint, date: date)
            }

            Rectangle().fill(.white.opacity(0.08)).frame(height: 0.5)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(isCodex ? "クレジット" : (provider.window("model_weekly")?.label ?? "モデル週"))
                    .font(.system(size: 9)).foregroundStyle(BoardStyle.muted)
                    .lineLimit(1).minimumScaleFactor(0.7)
                Spacer(minLength: 2)
                if isCodex {
                    Text(creditText).font(.system(size: 16, weight: .semibold)).monospacedDigit()
                        .lineLimit(1).minimumScaleFactor(0.65)
                } else {
                    Text(modelText).font(.system(size: 16, weight: .semibold)).monospacedDigit()
                }
            }
            HStack(spacing: 3) {
                if stale { Image(systemName: "clock.badge.exclamationmark").font(.system(size: 8)) }
                Spacer(minLength: 0)
                Text(statusText).font(.system(size: 9)).lineLimit(1).minimumScaleFactor(0.75)
            }
            .foregroundStyle(stale ? Color.orange.opacity(0.9) : BoardStyle.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    private var creditText: String {
        guard let string = provider.credits, let value = Decimal(string: string, locale: Locale(identifier: "en_US_POSIX")) else { return "—" }
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 2
        return formatter.string(from: value as NSDecimalNumber) ?? "—"
    }

    private var modelText: String {
        guard let value = provider.window("model_weekly")?.remaining(at: date) else { return "—" }
        return "\(Int(value.rounded(.down)))%"
    }

    private var statusText: String {
        guard let measured = provider.measuredAt else {
            return provider.status == "error" ? "取得できません" : "未接続"
        }
        let sameDay = Calendar.current.isDate(measured, inSameDayAs: date)
        let formatter = DateFormatter()
        formatter.dateFormat = sameDay ? "HH:mm" : "M/d HH:mm"
        return "\(stale ? "更新待ち" : "取得") \(formatter.string(from: measured))"
    }
}

private struct QuotaCell: View {
    let window: UsageWindow?
    let label: String
    let tint: Color
    let date: Date

    private var remaining: Double? { window?.remaining(at: date) }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.system(size: 10)).foregroundStyle(BoardStyle.muted)
            HStack(alignment: .firstTextBaseline, spacing: 1) {
                Text(remaining.map { String(Int($0.rounded(.down))) } ?? "—")
                    .font(.system(size: 27, weight: .semibold)).monospacedDigit()
                if remaining != nil { Text("%").font(.system(size: 11)).foregroundStyle(BoardStyle.muted) }
            }
            GeometryReader { geometry in
                Capsule().fill(.white.opacity(0.13))
                    .overlay(alignment: .leading) {
                        Capsule().fill(tint).frame(width: geometry.size.width * (remaining ?? 0) / 100)
                    }
            }
            .frame(height: 3)
            Text(resetText).font(.system(size: 8)).foregroundStyle(BoardStyle.muted)
                .lineLimit(1).minimumScaleFactor(0.65)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(label)、残り\(remaining.map { "\(Int($0))パーセント" } ?? "未取得")、\(resetText)")
    }

    private var resetText: String {
        guard let window else { return "未取得" }
        guard let reset = window.resetsAt else { return window.resetLabel ?? "" }
        let minutes = Int(ceil(reset.timeIntervalSince(date) / 60))
        guard minutes > 0 else { return "更新待ち" }
        let hours = minutes / 60
        if hours >= 24 { return "↻ \(hours / 24)日\(hours % 24)時間" }
        if hours > 0 { return "↻ \(hours)時間\(minutes % 60)分" }
        return "↻ \(minutes)分"
    }
}

struct ClaudeMark: Shape {
    func path(in rect: CGRect) -> Path {
        var result = Path()
        let center = CGPoint(x: rect.midX, y: rect.midY)
        let outer = min(rect.width, rect.height) / 2
        for index in 0..<12 {
            let angle = Double(index) * .pi / 6
            let length = outer * (index.isMultiple(of: 2) ? 1 : 0.82)
            let direction = CGVector(dx: cos(angle), dy: sin(angle))
            let side = CGVector(dx: -direction.dy * 1.1, dy: direction.dx * 1.1)
            result.move(to: CGPoint(x: center.x + side.dx, y: center.y + side.dy))
            result.addLine(to: CGPoint(x: center.x + direction.dx * length + side.dx * 0.65,
                                      y: center.y + direction.dy * length + side.dy * 0.65))
            result.addLine(to: CGPoint(x: center.x + direction.dx * length - side.dx * 0.65,
                                      y: center.y + direction.dy * length - side.dy * 0.65))
            result.addLine(to: CGPoint(x: center.x - side.dx, y: center.y - side.dy))
            result.closeSubpath()
        }
        result.addEllipse(in: CGRect(x: center.x - 2.5, y: center.y - 2.5, width: 5, height: 5))
        return result
    }
}
