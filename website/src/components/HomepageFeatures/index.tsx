import React from 'react';
import clsx from 'clsx';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  description: React.ReactNode;
};

const FEATURES: FeatureItem[] = [
  {
    title: 'Connect from Codex / Claude / Cursor / Continue',
    description: (
      <>
        Works with popular AI tools via MCP Streamable HTTP, with copy/paste-ready configuration
        snippets.
      </>
    )
  },
  {
    title: 'Tools-first MCP server',
    description: (
      <>
        Purpose-built tools for inspecting fonts, glyphs, masters, kerning, spacing, and more—no
        brittle UI automation required.
      </>
    )
  },
  {
    title: 'Safe edits (confirm-gated; no auto-save)',
    description: (
      <>
        Mutating actions are explicit and confirm-gated, and the plug-in never auto-saves fonts to
        disk.
      </>
    )
  },
  {
    title: 'Kerning worklists + collision guard',
    description: (
      <>
        Generate relevance-based kerning worklists and detect collisions/near-misses with
        geometry-based measurements.
      </>
    )
  },
  {
    title: 'Spacing review/apply workflow',
    description: (
      <>
        Review spacing suggestions, preview changes with a dry-run, then apply conservatively when
        you approve.
      </>
    )
  },
  {
    title: 'Bundled docs search (docs_search / docs_get)',
    description: (
      <>
        Query the bundled Glyphs ObjectWrapper docs from your agent, on-demand, without flooding the
        client with thousands of resources.
      </>
    )
  }
];

export default function HomepageFeatures(): React.ReactElement {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={styles.header}>
          <h2>Designed for real font work</h2>
          <p>Fast setup, clean docs, and workflows that keep you in control.</p>
        </div>
        <div className={clsx('row', styles.grid)}>
          {FEATURES.map((feature, index) => (
            <div key={index} className={clsx('col col--4', styles.cardCol)}>
              <div className={styles.card}>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

