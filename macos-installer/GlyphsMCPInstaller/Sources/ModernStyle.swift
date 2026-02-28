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

struct WindowConfigurator: NSViewRepresentable {
	var configure: (NSWindow) -> Void

	func makeNSView(context: Context) -> NSView {
		let view = NSView()
		DispatchQueue.main.async {
			guard let window = view.window else { return }
			configure(window)
		}
		return view
	}

	func updateNSView(_ nsView: NSView, context: Context) {
		DispatchQueue.main.async {
			guard let window = nsView.window else { return }
			configure(window)
		}
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

