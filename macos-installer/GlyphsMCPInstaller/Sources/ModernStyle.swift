import AppKit
import SwiftUI

struct VisualEffectBackground: NSViewRepresentable {
	let material: NSVisualEffectView.Material
	let blendingMode: NSVisualEffectView.BlendingMode
	let state: NSVisualEffectView.State

	init(material: NSVisualEffectView.Material = .underWindowBackground,
	     blendingMode: NSVisualEffectView.BlendingMode = .behindWindow,
	     state: NSVisualEffectView.State = .active) {
		self.material = material
		self.blendingMode = blendingMode
		self.state = state
	}

	func makeNSView(context: Context) -> NSVisualEffectView {
		let view = NSVisualEffectView()
		view.material = material
		view.blendingMode = blendingMode
		view.state = state
		return view
	}

	func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
		nsView.material = material
		nsView.blendingMode = blendingMode
		nsView.state = state
	}
}

/// One surface for catalog cards, project templates, and grouped settings.
struct DesktopCardSurface: ViewModifier {
	@Environment(\.colorSchemeContrast) private var contrast

	func body(content: Content) -> some View {
		content
			.background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
			.overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
				.strokeBorder(Color.primary.opacity(contrast == .increased ? 0.25 : 0.08)))
	}
}

struct DesktopCard<Content: View>: View {
	var padding: CGFloat = 16
	@ViewBuilder var content: () -> Content

	var body: some View {
		content().padding(padding)
			.frame(maxWidth: .infinity, alignment: .leading)
			.modifier(DesktopCardSurface())
	}
}

/// Skills omit the preview; components and agents retain their own artwork.
struct DesktopCatalogCard<Preview: View, Title: View, Detail: View, Status: View, Actions: View, Footer: View>: View {
	var previewHeight: CGFloat? = 92
	var detailMinimumHeight: CGFloat = 64
	@ViewBuilder var preview: () -> Preview
	@ViewBuilder var title: () -> Title
	@ViewBuilder var detail: () -> Detail
	@ViewBuilder var status: () -> Status
	@ViewBuilder var actions: () -> Actions
	@ViewBuilder var footer: () -> Footer

	var body: some View {
		DesktopCard {
			VStack(alignment: .leading, spacing: 12) {
				if let previewHeight {
					preview().frame(maxWidth: .infinity).frame(height: previewHeight)
						.background(Color.blue.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
						.clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
						.accessibilityHidden(true)
				}
				title().font(.headline)
				detail().font(.callout).foregroundStyle(.secondary)
					.fixedSize(horizontal: false, vertical: true)
					.frame(maxWidth: .infinity, minHeight: detailMinimumHeight, alignment: .topLeading)
				Spacer(minLength: 4)
				status()
				actions()
				footer().font(.caption)
			}.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
		}
	}
}

struct DesktopStatus: View {
	enum Tone { case installed, neutral, progress, attention }
	let title: String
	var tone: Tone = .neutral
	var symbol: String = "circle"
	var spinning = false

	private var color: Color {
		switch tone {
		case .installed: return .green
		case .neutral: return .secondary
		case .progress: return .blue
		case .attention: return .orange
		}
	}

	var body: some View {
		HStack(spacing: 7) {
			if spinning { ProgressView().controlSize(.small).tint(color).accessibilityHidden(true) }
			else { Image(systemName: symbol).accessibilityHidden(true) }
			Text(LocalizedStringKey(title))
		}.font(.callout.weight(.medium)).foregroundStyle(color)
			.accessibilityElement(children: .combine)
	}
}

/// System styles retain keyboard focus, disabled appearance, and OS adaptations.
struct DesktopSecondaryButtonStyle: PrimitiveButtonStyle {
	func makeBody(configuration: Configuration) -> some View {
		Button(role: configuration.role, action: configuration.trigger) { configuration.label }
			.buttonStyle(.bordered).buttonBorderShape(.capsule).tint(.gray)
	}
}

struct DesktopActionButton: View {
	enum Emphasis { case primary, secondary }
	let title: String
	var symbol: String? = nil
	var emphasis: Emphasis = .secondary
	let action: () -> Void

	@ViewBuilder private var label: some View {
		if let symbol { Label(LocalizedStringKey(title), systemImage: symbol) }
		else { Text(LocalizedStringKey(title)) }
	}

	var body: some View {
		Group {
			if emphasis == .primary {
				Button(action: action) { label }.buttonStyle(.borderedProminent).tint(.blue)
			} else {
				Button(action: action) { label }.buttonStyle(DesktopSecondaryButtonStyle())
			}
		}.buttonBorderShape(.capsule).controlSize(.regular)
			.fixedSize(horizontal: true, vertical: false)
	}
}

/// Preserve readable labels when a card or translation needs more room.
struct DesktopActionRow<Content: View>: View {
	@ViewBuilder var content: () -> Content

	var body: some View {
		ViewThatFits(in: .horizontal) {
			HStack(spacing: 8) { content() }.fixedSize(horizontal: true, vertical: false)
			VStack(alignment: .leading, spacing: 8) { content() }
		}.frame(maxWidth: .infinity, alignment: .leading)
	}
}

struct DesktopTextLink: View {
	let title: LocalizedStringKey
	let destination: URL

	init(_ title: LocalizedStringKey, destination: URL) {
		self.title = title
		self.destination = destination
	}

	var body: some View {
		Link(title, destination: destination).buttonStyle(.link).tint(.blue)
	}
}

struct DesktopGroupBoxStyle: GroupBoxStyle {
	func makeBody(configuration: Configuration) -> some View {
		DesktopCard {
			VStack(alignment: .leading, spacing: 12) {
				configuration.label.font(.headline).foregroundStyle(.primary)
				configuration.content
			}
		}
	}
}

struct DesktopDesign: ViewModifier {
	func body(content: Content) -> some View {
		content.buttonStyle(DesktopSecondaryButtonStyle()).buttonBorderShape(.capsule).tint(.blue)
			.groupBoxStyle(DesktopGroupBoxStyle())
	}
}

extension View {
	func desktopDesign() -> some View { modifier(DesktopDesign()) }
}
