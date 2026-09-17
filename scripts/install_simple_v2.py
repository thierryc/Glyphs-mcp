#!/usr/bin/env python3
"""Install selected lean components with durable, whole-installation rollback."""
import argparse
from contextlib import ExitStack
import fcntl
import importlib.util
import json
import os
import platform
import re
import plistlib
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from build_simple_v2 import _identity
from installation_transaction import InstallationTransaction, write_json

LABEL = 'com.ap.cx.glyphs-mcp-sidecar'
COMPONENTS = ('mcp', 'curve-inspector', 'reference-inspector')


def restart_agent(agent, uid):
    domain = 'gui/' + str(uid)
    subprocess.run(['launchctl','bootout',domain+'/'+LABEL],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for attempt in range(40):
        result = subprocess.run(['launchctl','bootstrap',domain,str(agent)],capture_output=True,text=True)
        if result.returncode == 0:
            if not plistlib.loads(Path(agent).read_bytes()).get('RunAtLoad', False):
                subprocess.run(['launchctl','kickstart',domain+'/'+LABEL],check=True,capture_output=True)
            return
        if result.returncode != 5 or attempt == 39:
            raise RuntimeError(result.stderr.strip() or 'The sidecar could not start')
        time.sleep(.25)


def installed_components(root, plugins):
    receipt = root/'installation.json'
    if receipt.exists():
        data = json.loads(receipt.read_text())
        if 'components' in data: return set(data['components'])
    names = {'mcp': 'Glyphs MCP Bridge.glyphsPlugin', 'curve-inspector': 'Glyphs Curve Inspector.glyphsReporter',
             'reference-inspector': 'Glyphs Reference Inspector.glyphsReporter'}
    return {key for key, name in names.items() if (plugins/name).exists()}


def service_controller(build, home):
    specification = importlib.util.spec_from_file_location('glyphs_install_control', build/'sidecar/glyphs_mcp_sidecar/control.py')
    module = importlib.util.module_from_spec(specification)
    # Read the verified source directly: importing must not create bytecode in
    # the immutable payload, even when a command-line caller omitted python -B.
    exec(compile(Path(specification.origin).read_bytes(), specification.origin, 'exec'), module.__dict__)
    return module.ServerControl(home)


def install(build, home, python, application, companions=(), *, mcp=True, remove_components=(),
            only_components=(), start=False):
    build, home = Path(build).resolve(), Path(home).expanduser().resolve()
    application = Path(application).resolve()
    app_info = plistlib.loads((application/'Contents/Info.plist').read_bytes())
    if app_info.get('CFBundleIdentifier') != 'com.GeorgSeifert.Glyphs4':
        raise ValueError('Select a Glyphs 4 application for the lean components')
    manifest = json.loads((build/'manifest.json').read_text())
    available = {item['id']: item for item in manifest['companions']}
    expected = {'mcp': 'Glyphs MCP Bridge.glyphsPlugin', 'curve-inspector': 'Glyphs Curve Inspector.glyphsReporter',
                'reference-inspector': 'Glyphs Reference Inspector.glyphsReporter'}
    if set(available) != set(expected)-{'mcp'} or len(manifest['companions']) != 2 or manifest['bridge']['bundle'] != expected['mcp']:
        raise ValueError('Invalid component manifest')
    if any(item['bundle'] != expected[name] for name,item in available.items()):
        raise ValueError('Invalid companion bundle path')
    for architecture, item in manifest.get('runtimes', {}).items():
        if architecture not in ('arm64','x86_64') or item['path'] != 'runtimes/'+architecture or item['python'] != 'bin/python3' or item['glyphsCLI'] != 'bin/glyphs':
            raise ValueError('Invalid private runtime path')
    requested = set(companions) | ({'mcp'} if mcp else set())
    removed = set(remove_components)
    only = set(only_components)
    if (requested | removed | only) - set(COMPONENTS) or requested & removed:
        raise ValueError('Unknown or conflicting component selection')
    support = home/'Library/Application Support'
    root, plugins = support/'Glyphs MCP/lean-v2', support/'Glyphs 4/Plugins'
    # Verify every shipped component before touching the installation.
    checks = [(build/'sidecar', manifest['sidecar']['identity']),
              (build/manifest['bridge']['bundle'], manifest['bridge']['identity'])]
    checks += [(build/item['bundle'], item['identity']) for item in available.values()]
    checks += [(build/item['path'], item['identity']) for item in manifest.get('runtimes', {}).values()]
    for source, identity in checks:
        if _identity(source) != identity: raise ValueError('Build identity mismatch: '+source.name)
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.install.lock').open('a') as lock, ExitStack() as controls:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error: raise RuntimeError('Another installation is already running') from error
        allowed = {root/'sidecar', root/'runtime', root/'installation.json',
                   home/'Library/LaunchAgents'/(LABEL+'.plist'),
                   *(plugins/name for name in expected.values()),
                   plugins/'Glyphs MCP Bridge.glyphsPalette', plugins/'Glyphs MCP.glyphsPlugin'}
        controller = service_controller(build, home)
        controls.enter_context(controller.exclusive())
        pending = [json.loads(path.read_text()) for path in root.glob('transaction-*/journal.json')]
        interrupted = [item for item in pending if item['state'] not in ('committed', 'restored')
                       and any(entry['started'] for entry in item['entries'])]
        # Recover files only after a fresh idle check of a surviving process.
        if interrupted and controller.agent.exists() and controller.status()['loaded']:
            controller._run('stop')
        # Recover the receipt before deriving upgrade choices from it.
        recovered = InstallationTransaction.recover(root, allowed)
        previous_agent = home/'Library/LaunchAgents'/(LABEL+'.plist')
        if previous_agent.is_file() and any(item.get('serviceWasStopped') or any(entry['started'] for entry in item['entries']) and item.get('launchAgentWasLoaded') for item in recovered):
            restart_agent(previous_agent, os.getuid())
        existing = installed_components(root, plugins)
        selected = (existing | requested) - removed
        # --only scopes the transaction. A scoped removal deliberately names
        # an item that will not remain selected, so only surviving items are
        # replacement sources while the removed item is still journaled.
        replaced = only - removed if only else set(selected)
        if not only <= selected | removed or not replaced <= selected:
            raise ValueError('A replacement-only component must be selected or removed')
        needs_runtime = bool(selected & {'mcp', 'reference-inspector'})
        runtime = manifest.get('runtimes', {}).get(platform.machine()) if needs_runtime else None
        if needs_runtime and manifest.get('runtimes') and runtime is None:
            raise ValueError('This installer has no runtime for this Mac architecture')
        python = (root/'runtime'/runtime['python'] if runtime else Path(python).absolute() if python else None) if needs_runtime else None
        if needs_runtime and (python is None or not runtime and not python.is_file()):
            raise ValueError('The bundled Python runtime is missing')
        sources = []
        if needs_runtime and runtime and replaced & {'mcp', 'reference-inspector'}:
            sources.append((build/runtime['path'], root/'runtime', runtime['identity']))
        if 'mcp' in replaced:
            sources.append((build/'sidecar', root/'sidecar', manifest['sidecar']['identity']))
        bundles = {'mcp': manifest['bridge'], **available}
        sources.extend((build/bundles[name]['bundle'], plugins/bundles[name]['bundle'], bundles[name]['identity'])
                       for name in COMPONENTS if name in replaced)
        return _replace(build, home, root, plugins, application, manifest, selected, removed, replaced,
                        sources, python, runtime, start, controller)


def _replace(build, home, root, plugins, application, manifest, selected, removed, replaced,
             sources, python, runtime, start, controller):
    agent = home/'Library/LaunchAgents'/(LABEL+'.plist')
    receipt_path = root/'installation.json'
    removals = [plugins/name for name in ('Glyphs MCP Bridge.glyphsPalette', 'Glyphs MCP.glyphsPlugin')
                if ('mcp' in selected or 'mcp' in removed) and ((plugins/name).exists() or (plugins/name).is_symlink())]
    # Only replace the known MCP plugin, never a different same-named bundle.
    for target in removals:
        info = target/'Contents/Info.plist'
        if target.name == 'Glyphs MCP.glyphsPlugin':
            if not info.is_file() or plistlib.loads(info.read_bytes()).get('CFBundleIdentifier') != 'com.Thierry Charbonnel.MCPBridgePlugin':
                raise ValueError('An unrecognized plugin occupies '+str(target))
    bundles = {'mcp': manifest['bridge'], **{item['id']: item for item in manifest['companions']}}
    removals.extend(plugins/bundles[name]['bundle'] for name in removed)
    if 'mcp' in removed: removals.extend([root/'sidecar', agent])
    if not selected & {'mcp','reference-inspector'} and removed: removals.append(root/'runtime')
    old_agent = agent.read_bytes() if agent.exists() else None
    settings = plistlib.loads(old_agent) if old_agent else {}
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    args = settings.get('ProgramArguments', [])
    port = args[args.index('--port')+1] if '--port' in args else str(previous.get('port', 9680))
    automatic = bool(settings.get('RunAtLoad', previous.get('autoStart', True)))
    logs = home/'Library/Logs/Glyphs MCP'
    cli = str(root/'runtime'/runtime['glyphsCLI']) if runtime else None
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=root) as tmp:
        temporary = Path(tmp)
        changes = [(source, target) for source, target, _ in sources]
        changes.extend((None, target) for target in removals)
        if 'mcp' in selected:
            logs.mkdir(parents=True, exist_ok=True)
            settings.update(Label=LABEL, ProgramArguments=[str(python), str(root/'sidecar/run.py'),
                '--transport','http','--port',str(port),'--glyphs-app',str(application)],
                RunAtLoad=automatic, KeepAlive=automatic, ThrottleInterval=10,
                StandardOutPath=str(logs/'sidecar.log'), StandardErrorPath=str(logs/'sidecar-error.log'))
            settings['AssociatedBundleIdentifiers'] = ['cx.ap.glyphsMcp']
            settings['EnvironmentVariables'] = {**settings.get('EnvironmentVariables', {}),
                'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
            if cli: settings['EnvironmentVariables']['GLYPHS_MCP_GLYPHS_CLI'] = cli
            staged_agent = temporary/agent.name
            staged_agent.write_bytes(plistlib.dumps(settings,sort_keys=True))
            changes.append((staged_agent, agent))
        replaced_targets = {str(target) for _, target, _ in sources}
        removed_names = {bundles[name]['bundle'] for name in removed}
        removed_targets = {str(target) for target in removals}
        prior_installed = [item for item in previous.get('installed', [])
                           if item.get('path') not in replaced_targets
                           and Path(item.get('path', '')).name not in removed_names
                           and item.get('path') not in removed_targets]
        result = {'schemaVersion':2,'version':manifest['projectVersion'],'installerBuild':manifest['installerBuild'],'bridgeVersion':manifest['version'],
            'build':str(build),'components':sorted(selected),'application':str(application),
            'installed':prior_installed + [{'path':str(target),'identity':identity} for _,target,identity in sources],
            'launchAgent':str(agent) if 'mcp' in selected else None,'python':str(python) if python else None,
            'glyphsCLI':cli,'restartGlyphsRequired':True,'port':int(port),'autoStart':automatic}
        prior_details = previous.get('componentDetails', {})
        result['componentDetails'] = {name: (
            {**manifest.get('components', {}).get(name, {}), 'version': manifest.get('projectVersion', '2.0.0'),
             'identity': bundles[name]['identity']} if name in replaced or name not in prior_details
            else prior_details[name]) for name in selected}
        runtime_changed = bool(replaced & {'mcp','reference-inspector'})
        result['runtime'] = ({**runtime, 'architecture':platform.machine(), 'installedPath':str(root/'runtime')}
            if runtime and selected & {'mcp','reference-inspector'} and runtime_changed
            else previous.get('runtime') if selected & {'mcp','reference-inspector'} else None)
        result['bridge'] = ({**manifest['bridge'], 'version':manifest['version']} if 'mcp' in replaced
            else previous.get('bridge')) if 'mcp' in selected else None
        result['sidecar'] = ({**manifest['sidecar'], 'requires':['runtime']} if 'mcp' in replaced
            else previous.get('sidecar')) if 'mcp' in selected else None
        previous_companions = {item.get('id'): item for item in previous.get('companions', [])}
        result['companions'] = [(item if item['id'] in replaced or item['id'] not in previous_companions
                                 else previous_companions[item['id']])
                                for item in manifest['companions'] if item['id'] in selected]
        staged_receipt = temporary/'installation.json'
        staged_receipt.write_text(json.dumps(result,indent=2)+'\n')
        changes.append((staged_receipt, receipt_path))
        transaction = InstallationTransaction(root, changes)
        result['backup'] = str(transaction.backup)
        # The receipt points to the exact recovery material for this installation.
        Path(transaction.data['entries'][-1]['stage']).write_text(json.dumps(result,indent=2)+'\n')
        # Startup is a post-install choice. Every replacement first stops an
        # existing service through the shared idle guard, including removals.
        agent_was_loaded = controller.status()['loaded'] if agent.exists() else False
        transaction.data['launchAgentWasLoaded'] = agent_was_loaded
        write_json(transaction.journal, transaction.data)
        if agent_was_loaded:
            try:
                controller._run('stop')
            except BaseException:
                transaction.rollback()
                shutil.rmtree(transaction.stage)
                raise
            transaction.data['serviceWasStopped'] = True
            write_json(transaction.journal, transaction.data)
        def verify():
            for _, target, identity in sources:
                if _identity(target) != identity: raise RuntimeError('Installed identity mismatch: '+str(target))
            if runtime and selected & {'mcp','reference-inspector'}:
                subprocess.run([str(python), '-I', '-B', '-c', 'import fastmcp, glyphs_cli'], check=True,capture_output=True,timeout=30)
            if start and 'mcp' in selected and (agent_was_loaded or old_agent is None): restart_agent(agent, os.getuid())
        try:
            def stop_replacement():
                if agent.exists() and controller.status()['loaded']:
                    controller._run('stop')
            transaction.apply(verify, before_rollback=stop_replacement)
        except BaseException:
            if transaction.data['state'] == 'restored' and agent_was_loaded and old_agent and agent.exists():
                restart_agent(agent, os.getuid())
            raise
    return result


def preflight(build, application):
    manifest = json.loads((build/'manifest.json').read_text())
    runtime = manifest.get('runtimes', {}).get(platform.machine())
    if runtime is None: raise ValueError('The installer runtime is missing for this Mac')
    cli = build/runtime['path']/runtime['glyphsCLI']
    # The native worker uses the exact selected Glyphs application's scripting
    # environment. Private sidecar Python is intentionally a separate process.
    result = subprocess.run([str(cli),'run','--quiet','--app',str(application),'--plugins','',
        '-c','from GlyphsApp import GSFont; print("GLYPHS_MCP_NATIVE_READY")'],capture_output=True,text=True,timeout=45)
    if result.returncode or 'GLYPHS_MCP_NATIVE_READY' not in result.stdout:
        raise ValueError('Glyphs scripting is not ready. Enable Python in Glyphs Plugin Manager, then try again. '+result.stderr[-600:])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,default=Path(__file__).resolve().parents[1]/'build/simple-v2')
    parser.add_argument('--home',type=Path,default=Path.home())
    parser.add_argument('--python',type=Path)
    parser.add_argument('--glyphs-app',required=True,type=Path)
    parser.add_argument('--companion',action='append',default=[])
    parser.add_argument('--no-mcp',action='store_true')
    parser.add_argument('--remove',action='append',default=[],choices=COMPONENTS)
    parser.add_argument('--only',action='append',default=[],choices=COMPONENTS,
                        help='Replace only these selected components; preserve other installed bundles.')
    parser.add_argument('--start',action='store_true')
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    if args.preflight_only or not (args.no_mcp and not args.companion and args.remove):
        preflight(args.build,args.glyphs_app)
    if args.preflight_only:
        print(json.dumps({'ok':True})); return
    executable = args.glyphs_app.resolve() / 'Contents/MacOS'
    for pattern in ('^'+re.escape(str(executable))+'/', 'glyphs_mcp_sidecar.native_worker'):
        if subprocess.run(['/usr/bin/pgrep','-f',pattern],stdout=subprocess.DEVNULL).returncode == 0:
            raise ValueError('Close Glyphs and wait for active font tasks to finish before installing.')
    result=install(args.build,args.home,args.python,args.glyphs_app,args.companion,
                   mcp=not args.no_mcp,remove_components=args.remove,
                   only_components=args.only,start=args.start)
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'ok':False,'error':{'message':str(error)}}))
        raise SystemExit(1)
