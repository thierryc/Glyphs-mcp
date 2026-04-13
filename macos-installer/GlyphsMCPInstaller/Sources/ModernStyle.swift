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

struct GlassGroupBoxStyle: GroupBoxStyle {
	func makeBody(configuration: Configuration) -> some View {
		VStack(alignment: .leading, spacing: 10) {
			configuration.label
				.font(.headline)
				.foregroundStyle(.primary)
			configuration.content
		}
		.padding(14)
		.background(
			RoundedRectangle(cornerRadius: 14, style: .continuous)
				.fill(.regularMaterial)
		)
		.overlay(
			RoundedRectangle(cornerRadius: 14, style: .continuous)
				.strokeBorder(.white.opacity(0.08))
		)
	}
}

struct PrimaryHeroButtonStyle: ButtonStyle {
	@Environment(\.isEnabled) private var isEnabled

	func makeBody(configuration: Configuration) -> some View {
		configuration.label
			.font(.headline.weight(.semibold))
			.foregroundStyle(.white.opacity(isEnabled ? 1 : 0.72))
			.padding(.horizontal, 30)
			.padding(.vertical, 14)
			.frame(minWidth: 280)
			.background(
				Capsule(style: .continuous)
					.fill(backgroundColor(pressed: configuration.isPressed))
			)
			.overlay(
				Capsule(style: .continuous)
					.strokeBorder(.white.opacity(isEnabled ? 0.12 : 0.05))
			)
			.scaleEffect(configuration.isPressed && isEnabled ? 0.985 : 1)
			.shadow(color: .black.opacity(isEnabled ? 0.14 : 0.05), radius: 12, y: 6)
			.animation(.easeOut(duration: 0.12), value: configuration.isPressed)
	}

	private func backgroundColor(pressed: Bool) -> Color {
		guard isEnabled else { return .accentColor.opacity(0.34) }
		return .accentColor.opacity(pressed ? 0.78 : 0.94)
	}
}

struct SecondaryPillButtonStyle: ButtonStyle {
	@Environment(\.isEnabled) private var isEnabled

	func makeBody(configuration: Configuration) -> some View {
		configuration.label
			.font(.subheadline.weight(.semibold))
			.foregroundStyle(foregroundColor)
			.padding(.horizontal, 18)
			.padding(.vertical, 10)
			.background(
				Capsule(style: .continuous)
					.fill(backgroundMaterialOpacity(pressed: configuration.isPressed))
			)
			.overlay(
				Capsule(style: .continuous)
					.strokeBorder(borderColor(pressed: configuration.isPressed))
			)
			.scaleEffect(configuration.isPressed && isEnabled ? 0.988 : 1)
			.animation(.easeOut(duration: 0.12), value: configuration.isPressed)
	}

	private var foregroundColor: Color {
		isEnabled ? .primary : .secondary.opacity(0.7)
	}

	private func backgroundMaterialOpacity(pressed: Bool) -> Color {
		if !isEnabled { return .white.opacity(0.03) }
		return .white.opacity(pressed ? 0.12 : 0.08)
	}

	private func borderColor(pressed: Bool) -> Color {
		if !isEnabled { return .white.opacity(0.05) }
		return .white.opacity(pressed ? 0.22 : 0.14)
	}
}
