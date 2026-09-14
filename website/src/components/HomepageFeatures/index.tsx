import React from 'react';
import Link from '@docusaurus/Link';
import clsx from 'clsx';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  description: React.ReactNode;
};

const FEATURES: FeatureItem[] = [
  {title: 'Install and connect', description: <>Follow the setup for <Link to="/docs/getting-started/installation">v1</Link> or <Link to="/docs/v2/getting-started/installation">v2</Link>, then check the connection from your AI client.</>},
  {title: 'Use the matching tools', description: <>Browse the <Link to="/docs/reference/command-set">v1 catalog</Link> or the <Link to="/docs/v2/reference/command-set">seven v2 tools</Link>. Each guide describes its own supported workflows.</>},
  {title: 'Review in Glyphs', description: <>Learn the <Link to="/docs/v2/concepts/safety-model">v2 Save, Undo and recovery workflow</Link> and use the <Link to="/docs/v2/workflows/visual-review">optional inspectors</Link> to examine changes.</>}
];

export default function HomepageFeatures(): React.ReactElement {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={styles.header}>
          <h2>Find your next step</h2>
          <p>Setup, tools and review are documented separately for each version.</p>
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
