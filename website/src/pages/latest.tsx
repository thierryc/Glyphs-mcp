import React, {useEffect} from 'react';
import Layout from '@theme/Layout';
import useBaseUrl from '@docusaurus/useBaseUrl';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import ExecutionEnvironment from '@docusaurus/ExecutionEnvironment';

export default function Latest(): React.JSX.Element {
  const target = useBaseUrl('/docs/');
  const {siteConfig} = useDocusaurusContext();
  const version = (siteConfig.customFields as {legacyVersion?: string} | undefined)
    ?.legacyVersion;

  useEffect(() => {
    if (ExecutionEnvironment.canUseDOM) {
      window.location.replace(target);
    }
  }, [target]);

  return (
    <Layout title="Latest docs">
      <main className="container margin-vert--lg">
        <h1>Redirecting…</h1>
        <p>
          Sending you to the docs for {version ? `v${version}` : 'the latest release'}.
        </p>
        <p>
          If you are not redirected, <a href={target}>open the docs</a>.
        </p>
      </main>
    </Layout>
  );
}

