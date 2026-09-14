import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    'glyphs-mcp',
    {type: 'category', label: 'Getting Started', items: [
      'getting-started/installation', 'getting-started/desktop', 'tutorial/first-session',
      'getting-started/start-server', 'getting-started/connect-client',
      'getting-started/use-agent-skills', 'getting-started/migrate-from-v1',
      'getting-started/troubleshooting'
    ]},
    {type: 'category', label: 'How It Works', items: [
      'concepts/how-glyphs-mcp-works', 'concepts/safety-model', 'concepts/agent-skills'
    ]},
    {type: 'category', label: 'Workflows', items: [
      'workflows/projects', 'spacing-tools', 'kerning-workflow', 'italic-first-pass',
      'workflows/start-node-correspondence', 'workflows/visual-review'
    ]},
    {type: 'category', label: 'Reference', items: [
      'reference/command-set', 'reference/version-identity', 'reference/settings', 'reference/resources',
      'reference/glyphs3-compatibility'
    ]},
    {type: 'category', label: 'Contributors', items: [
      'contributor/local-docs-development', 'contributor/release-qa-protocol',
      'contributor/release-build-notes'
    ]}
  ]
};

export default sidebars;
