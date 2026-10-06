import React from 'react';
import Link from '@docusaurus/Link';
import clsx from 'clsx';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  description: React.ReactNode;
};

const FEATURES: FeatureItem[] = [
  {title: 'Install and connect', description: <>Use <Link to="/docs/v2/getting-started/installation">Setup</Link> to install the Glyphs components and configure your AI client, then check the connection.</>},
  {title: 'Prepare a small edit', description: <>Try the <Link to="/docs/v2/tutorial/first-session">first-session walkthrough</Link> on a disposable font. Explore the <Link to="/docs/v2/reference/command-set">thirteen v2 tools</Link> as you work.</>},
  {title: 'Review in Glyphs', description: <>Understand <Link to="/docs/v2/concepts/safety-model">Save, Undo and recovery</Link> and use the <Link to="/docs/v2/workflows/visual-review">optional inspectors</Link> to examine changes.</>}
];

export default function HomepageFeatures(): React.ReactElement {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={styles.header}>
          <h2>From connection to a reviewed edit</h2>
          <p>Start small, inspect the result and choose what to keep.</p>
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
