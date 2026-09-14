import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import HomepageFeatures from '../components/HomepageFeatures';
import styles from './index.module.css';

export default function Home(): React.JSX.Element {
  const {siteConfig} = useDocusaurusContext();
  const {gmcpVersion, legacyVersion} = siteConfig.customFields as {
    gmcpVersion: string; legacyVersion: string;
  };

  return (
    <Layout title="Documentation for v1 and v2" description="Choose the Glyphs MCP guide that matches your installation.">
      <header className={styles.heroBanner}>
        <div className={styles.heroInner}>
          <h1 className="hero__title">Glyphs MCP documentation</h1>
          <p className={styles.tagline}>
            Connect your AI application to Glyphs. Choose the guide that matches
            your installation, from the first connection to reviewing font changes.
          </p>
        </div>
      </header>
      <main>
        <section className={styles.section} aria-label="Choose your documentation version">
          <div className={`container ${styles.versions}`}>
            <article className={styles.versionCard}>
              <p className={styles.eyebrow}>Released · retained for Glyphs 3</p>
              <h2>v1 <small>{legacyVersion}</small></h2>
              <p>The original plugin, its command catalog, installation guide and workflow documentation, preserved from the release.</p>
              <Link className="button button--secondary button--lg" to="/docs/">Read the v1 guide</Link>
              <p className={styles.secondaryLink}><Link to="/docs/getting-started/installation">v1 installation</Link></p>
            </article>
            <article className={`${styles.versionCard} ${styles.currentCard}`}>
              <p className={styles.eyebrow}>Glyphs 4 · local candidate</p>
              <h2>v2 <small>{gmcpVersion}</small></h2>
              <p>Seven tools, an external server, a private runtime and optional inspectors. The local installer is signed and notarized; public release is separate.</p>
              <Link className="button button--primary button--lg" to="/docs/v2/">Read the v2 guide</Link>
              <p className={styles.secondaryLink}><Link to="/docs/v2/getting-started/installation">v2 installation</Link></p>
            </article>
          </div>
          <p className={styles.migrationLink}>
            Already using v1? <Link to="/docs/v2/getting-started/migrate-from-v1">See what changes in v2.</Link>
          </p>
        </section>
        <HomepageFeatures />
        <section className={styles.section}>
          <div className={`container ${styles.quickstart}`}>
            <h2>Documentation that follows your version</h2>
            <p>Use the version selector to switch guides. Shared pages open their counterpart, while workflows unique to one version stay in that guide.</p>
            <p>Created by Thierry Charbonnel. <Link href="https://github.com/thierryc/Glyphs-mcp/issues">Report an issue</Link>, browse <Link href="https://github.com/thierryc/Glyphs-mcp/releases">published releases</Link>, or <Link href="https://github.com/sponsors/thierryc">support the project</Link>.</p>
          </div>
        </section>
      </main>
    </Layout>
  );
}
