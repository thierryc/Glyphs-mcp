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

  return (
    <Layout title={siteConfig.title} description={siteConfig.tagline}>
      <header className={styles.heroBanner}>
        <div className={styles.heroInner}>
          <h1 className="hero__title">Glyphs MCP</h1>
          <p className={styles.tagline}>
            A Model Context Protocol server for Glyphs that exposes font-specific tools to AI and
            LLM agents.
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
              <h2>Quickstart</h2>
              <ol>
                <li>
                  Install the plug-in with the guided installer: <code>python3 install.py</code>
                </li>
                <li>
                  In Glyphs, start the server: <strong>Edit → Start Glyphs MCP Server</strong>
                </li>
                <li>
                  Connect your client to <code>http://127.0.0.1:9680/mcp/</code>
                </li>
              </ol>

              <CodeBlock language="bash">{`python3 install.py
# In Glyphs: Edit → Start Glyphs MCP Server
# Connect: http://127.0.0.1:9680/mcp/`}</CodeBlock>

              <p>
                Supported clients include Codex CLI, Claude Desktop, Cursor, Windsurf, and Continue.
                See <Link to="/docs/getting-started/connect-client">Connect a client</Link>.
              </p>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}

