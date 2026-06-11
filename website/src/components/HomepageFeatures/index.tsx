import React from 'react';
import clsx from 'clsx';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  description: React.ReactNode;
};

const FEATURES: FeatureItem[] = [
  {
    title: 'Start from a health check',
    description: (
      <>
        Install the plug-in, start the local server, connect a client, then verify with
        list_open_fonts before doing font work.
      </>
    )
  },
  {
    title: 'Use tools before code',
    description: (
      <>
        Work through named tools for fonts, masters, glyphs, kerning, spacing, outlines, exports,
        and bundled docs lookup.
      </>
    )
  },
  {
    title: 'Keep edits controlled',
    description: (
      <>
        Read current state first, dry-run where possible, use confirm-gated mutations, and save only
        when you ask.
      </>
    )
  },
  {
    title: 'Run typographic workflows',
    description: (
      <>
        Follow focused docs for kerning, spacing, compensated tuning, style sets, outlines, and
        UFO/designspace export.
      </>
    )
  },
  {
    title: 'Pick smaller tool profiles',
    description: (
      <>
        Reduce client context by exposing only the tools needed for read-only, kerning, spacing,
        outline, or editing work.
      </>
    )
  },
  {
    title: 'Search bundled Glyphs docs',
    description: (
      <>
        Use docs_search and docs_get for targeted Glyphs API lookup without flooding the MCP client
        with page resources.
      </>
    )
  }
];

export default function HomepageFeatures(): React.ReactElement {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={styles.header}>
          <h2>Documentation paths</h2>
          <p>Start with setup, then move into the workflow or reference page for the task.</p>
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
