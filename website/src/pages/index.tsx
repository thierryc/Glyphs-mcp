import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import HomepageFeatures from '../components/HomepageFeatures';
import styles from './index.module.css';

// Keep the public download separate from the local documentation identity.
// Replace this pinned beta only after stable artifact qualification/publication.
const publishedDownload = {
  label: '2.0.0 Beta 11',
  build: 53,
  url: 'https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0-beta.11/Glyphs-MCP-2.0.0-beta.11.dmg',
  release: 'https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.11',
};

export default function Home(): React.JSX.Element {
  const {siteConfig} = useDocusaurusContext();
  const {gmcpVersion, legacyVersion} = siteConfig.customFields as {
    gmcpVersion: string; legacyVersion: string;
  };

  return (
    <Layout title="An AI companion for Glyphs 4" description="Connect your AI agent to Glyphs 4, prepare font edits and review the result. Install Glyphs MCP for macOS 14 or later.">
      <header className={styles.heroBanner}>
        <div className={styles.heroInner}>
          <p className={styles.eyebrow}>Glyphs 4 · macOS 14+</p>
          <h1 className="hero__title">Glyphs MCP v2</h1>
          <p className={styles.tagline}>
            An AI companion for your font work. Connect your agent to Glyphs,
            prepare edits and review the result while keeping control of your decisions.
          </p>
          <div className={styles.buttons}>
            <Link className="button button--primary button--lg" href={publishedDownload.url}>
              Download {publishedDownload.label}
            </Link>
            <Link className="button button--secondary button--lg" to="/docs/v2/tutorial/first-session">
              Try your first session
            </Link>
          </div>
          <p className={styles.releaseNote}>
            Public prerelease · build {publishedDownload.build}. Stable v2 qualification is in progress.{' '}
            <Link href={publishedDownload.release}>Release notes</Link>
          </p>
        </div>
      </header>
      <main>
        <section className={styles.section} aria-labelledby="requirements-title">
          <div className={`container ${styles.quickstart}`}>
            <h2 id="requirements-title">Start with Glyphs 4</h2>
            <p>
              Install Glyphs 4, launch it with your license or Continue Trial, and
              install Python through Glyphs' official Plugin Manager. Select the
              installed <strong>(Glyphs)</strong> Python under Settings → Addons,
              then save your work and quit Glyphs before installing the MCP components.
            </p>
            <dl className={styles.requirements}>
              <div><dt>Mac</dt><dd>macOS 14 or later</dd></div>
              <div><dt>Font editor</dt><dd>Glyphs 4 · license or trial</dd></div>
              <div><dt>AI client</dt><dd>Codex, Claude Code, Claude Desktop or Cursor</dd></div>
            </dl>
            <p>
              The native companion helps install the bridge, local server and optional
              inspectors, then configure your agent connection.{' '}
              <Link to="/docs/v2/getting-started/installation">Follow the installation guide</Link>.
            </p>
          </div>
        </section>
        <HomepageFeatures />
        <section className={styles.section} aria-label="Choose your documentation version">
          <div className={`container ${styles.versions}`}>
            <article className={`${styles.versionCard} ${styles.currentCard}`}>
              <p className={styles.eyebrow}>Primary guide · Glyphs 4</p>
              <h2>v2 <small>{gmcpVersion}</small></h2>
              <p>Thirteen tools, a separate local server, a private runtime and optional inspectors. This guide follows the unpublished 2.0.0/build 55 candidate. Guided Python setup and the Welcome screen are local v2 additions; the public download remains Beta 11.</p>
              <Link className="button button--primary button--lg" to="/docs/v2/">Read the v2 guide</Link>
              <p className={styles.secondaryLink}><Link to="/docs/v2/getting-started/migrate-from-v1">Moving from v1 to v2</Link></p>
            </article>
            <article className={styles.versionCard}>
              <p className={styles.eyebrow}>Released · retained for Glyphs 3</p>
              <h2>v1 <small>{legacyVersion}</small></h2>
              <p>The frozen v1.11.0 guide and separate pinned distribution remain available for Glyphs 3. The v2 installer is for Glyphs 4.</p>
              <Link className="button button--secondary button--lg" to="/docs/">Read the v1 guide</Link>
              <p className={styles.secondaryLink}><Link href="https://github.com/thierryc/Glyphs-mcp/releases/tag/v1.11.0">Glyphs 3 download</Link></p>
            </article>
          </div>
        </section>
        <section className={styles.section} aria-labelledby="limits-title">
          <div className={`container ${styles.quickstart}`}>
            <h2 id="limits-title">Before you try it</h2>
            <p>Begin with a disposable font and a small change. Supported operations depend on the connected bridge. Review results in Glyphs; accepting an edit and saving your font are separate actions.</p>
            <p>The native VM evidence covers Apple silicon on macOS 14.6.1. Exact macOS 14.0 and final signed-candidate acceptance remain pending; physical Intel testing is deferred. The independent Beztrace plugin has its own setup and qualification.</p>
            <p><Link href="https://github.com/thierryc/Glyphs-mcp/blob/lit/v2-beta/BETA.md">Read beta limitations and qualification notes</Link> or use <Link to="/docs/v2/getting-started/troubleshooting">troubleshooting</Link>.</p>
            <h2>Made with the community</h2>
            <p>Glyphs MCP is an open source project by Thierry Charbonnel. <Link href="https://github.com/thierryc/Glyphs-mcp/issues">Report an issue</Link>, explore the <Link href="https://github.com/thierryc/Glyphs-mcp">repository</Link>, or <Link href="https://github.com/sponsors/thierryc">support the project</Link>.</p>
          </div>
        </section>
      </main>
    </Layout>
  );
}
