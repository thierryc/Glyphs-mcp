import React from 'react';

import CodeBlock from '@theme/CodeBlock';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';

import HomepageFeatures from '../components/HomepageFeatures';
import styles from './index.module.css';

export default function Home(): React.JSX.Element {
  const {siteConfig} = useDocusaurusContext();
  const version = siteConfig.customFields?.gmcpVersion as string | undefined;

  return (
    <Layout title={siteConfig.title} description={siteConfig.tagline}>
      <header className={styles.heroBanner}>
        <div className={styles.heroInner}>
          <h1 className="hero__title">Glyphs MCP</h1>
          <p className={styles.tagline}>
            Canonical documentation for the Glyphs plug-in that exposes safe, font-specific
            Model Context Protocol tools to AI clients, with Glyphs 4 beta support on this branch.
          </p>
          <p className={styles.endpoint}>
            Local endpoint: <code>http://127.0.0.1:9680/mcp/</code>
          </p>
          <div className={styles.buttons}>
            <Link
              className="button button--primary button--lg"
              to="/docs/getting-started/installation"
            >
              Get started
            </Link>
            <Link
              className="button button--secondary button--lg"
              href="https://github.com/thierryc/Glyphs-mcp/releases/latest"
            >
              Latest release{version && version !== 'dev' ? ` v${version}` : ''}
            </Link>
            <Link
              className="button button--secondary button--lg"
              href="https://github.com/thierryc/Glyphs-mcp"
            >
              View on GitHub
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className={styles.section}>
          <div className="container">
            <img
              className={styles.screenshot}
              src={useBaseUrl('/img/GlyphsMcpScreenshot.png')}
              alt="Glyphs MCP screenshot"
              loading="lazy"
            />
          </div>
        </section>

        <HomepageFeatures />

        <section className={styles.section}>
          <div className="container">
            <div className={styles.quickstart}>
              <h2>First successful tool call</h2>
              <ol>
                <li>
                  Install the plug-in and dependencies: <code>python3 install.py</code>
                </li>
                <li>
                  In Glyphs, start the server: <strong>Edit -&gt; Glyphs MCP Server</strong>
                </li>
                <li>
                  Connect your client to <code>http://127.0.0.1:9680/mcp/</code>
                </li>
                <li>
                  Ask the client to call <code>list_open_fonts</code>.
                </li>
              </ol>

              <CodeBlock language="bash">{`python3 install.py
# In Glyphs: Edit -> Glyphs MCP Server
# Connect: http://127.0.0.1:9680/mcp/`}</CodeBlock>

              <p>
                Continue with <Link to="/docs/tutorial/first-session">First session</Link> or
                jump to <Link to="/docs/reference/command-set">Command set</Link>.
              </p>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
