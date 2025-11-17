#!/usr/bin/env node

const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const EventSource = require('eventsource');

class MCPSSEBridge {
    constructor(sseUrl) {
        this.sseUrl = sseUrl;
        this.server = new Server({
            name: 'mcp-sse-bridge',
            version: '1.0.0'
        }, {
            capabilities: {
                tools: {},
                resources: {},
                prompts: {}
            }
        });
        
        this.tools = new Map();
        this.resources = new Map();
        this.prompts = new Map();
        this.isInitialized = false;
        this.pendingRequests = new Map();
        this.sessionId = null;
        this.eventSource = null;
        this.requestId = 0;
    }

    async initialize() {
        if (this.isInitialized) return;
        
        try {
            // Connect to SSE stream
            await this.connectSSE();
            
            // Discover capabilities from the running server
            await this.discoverCapabilities();
            
            // Set up MCP server handlers
            this.setupHandlers();
            
            this.isInitialized = true;
            console.error('SSE Bridge initialized successfully');
        } catch (error) {
            console.error('Failed to initialize bridge:', error);
            throw error;
        }
    }

    async connectSSE() {
        return new Promise((resolve, reject) => {
            const headers = {};
            if (this.sessionId) {
                headers['Mcp-Session-Id'] = this.sessionId;
            }

            this.eventSource = new EventSource(this.sseUrl, { headers });
            
            this.eventSource.onopen = () => {
                console.error('SSE connection established');
                resolve();
            };

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                this.handleSSEMessage(data);
                } catch (error) {
                    console.error('Error processing SSE message:', error);
                }
            };

            this.eventSource.onerror = (error) => {
                console.error('SSE connection error:', error);
                if (!this.isInitialized) {
                    reject(error);
                } else {
                    // Attempt to reconnect after a delay
                    setTimeout(() => this.reconnectSSE(), 5000);
                }
            };
        });
    }

    async reconnectSSE() {
        if (this.eventSource) {
            this.eventSource.close();
        }
        
        try {
            await this.connectSSE();
            console.error('SSE reconnected successfully');
        } catch (error) {
            console.error('Failed to reconnect SSE:', error);
            setTimeout(() => this.reconnectSSE(), 5000);
        }
    }

    handleSSEMessage(data) {
        if (data.jsonrpc === '2.0') {
            if (data.id && this.pendingRequests.has(data.id)) {
                // This is a response to a request we made
                const { resolve, reject } = this.pendingRequests.get(data.id);
                this.pendingRequests.delete(data.id);
                
                if (data.error) {
                    reject(new Error(data.error.message || 'Unknown error'));
                } else {
                    resolve(data.result);
                }
            } else if (data.method) {
                // This is a notification from the server
                this.handleNotification(data);
            }
        }
    }

    handleNotification(data) {
        // Forward notifications to Claude Desktop
        if (data.method === 'notifications/resources/updated') {
            this.server.sendNotification('notifications/resources/updated', data.params);
        } else if (data.method === 'notifications/resources/list_changed') {
            this.server.sendNotification('notifications/resources/list_changed', data.params);
            // Refresh resources list
            this.discoverResources();
        } else if (data.method === 'notifications/tools/list_changed') {
            this.server.sendNotification('notifications/tools/list_changed', data.params);
            // Refresh tools list
            this.discoverTools();
        } else if (data.method === 'notifications/prompts/list_changed') {
            this.server.sendNotification('notifications/prompts/list_changed', data.params);
            // Refresh prompts list
            this.discoverPrompts();
        }
    }

    async sendSSERequest(method, params) {
        return new Promise((resolve, reject) => {
            const id = ++this.requestId;
            
            // Store the promise resolvers
            this.pendingRequests.set(id, { resolve, reject });
            
            // Allow callers to extend the wait window per request
            const timeoutSeconds = (params && typeof params.timeout === 'number' && params.timeout > 0)
                ? params.timeout
                : 60;
            const timeoutMs = timeoutSeconds * 1000;

            // Create the JSON-RPC request
            const request = {
                jsonrpc: '2.0',
                id: id,
                method: method,
                params: params
            };

            // Send request through SSE (this depends on your server implementation)
            // Most SSE servers expect requests to be sent through a different channel
            // We'll use a POST request to send the command, but receive response via SSE
            this.sendRequestToSSEServer(request);
            
            // Set timeout for the request
            setTimeout(() => {
                if (this.pendingRequests.has(id)) {
                    this.pendingRequests.delete(id);
                    reject(new Error('Request timeout'));
                }
            }, timeoutMs); // honour per-call timeout in seconds
        });
    }

    async sendRequestToSSEServer(request) {
        try {
            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream'
            };

            if (this.sessionId) {
                headers['Mcp-Session-Id'] = this.sessionId;
            }

            const response = await fetch(this.sseUrl, {
                method: 'POST',
                headers,
                body: JSON.stringify(request)
            });

            const incomingSession = response.headers.get('mcp-session-id');
            if (incomingSession && incomingSession !== this.sessionId) {
                this.sessionId = incomingSession;
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                const payload = await response.json();
                if (Array.isArray(payload)) {
                    payload.forEach(item => this.handleSSEMessage(item));
                } else {
                    this.handleSSEMessage(payload);
                }
            }
        } catch (error) {
            console.error('Error sending request to MCP server:', error);

            if (this.pendingRequests.has(request.id)) {
                const { reject } = this.pendingRequests.get(request.id);
                this.pendingRequests.delete(request.id);
                reject(error);
            }
        }
    }

    async discoverCapabilities() {
        try {
            // Initialize with the server
            const response = await this.sendSSERequest('initialize', {
                protocolVersion: '2024-11-05',
                capabilities: {
                    tools: {},
                    resources: {},
                    prompts: {}
                },
                clientInfo: {
                    name: 'mcp-sse-bridge',
                    version: '1.0.0'
                }
            });

            if (response.capabilities) {
                this.server.capabilities = response.capabilities;
            }

            // Discover tools, resources, and prompts
            await Promise.all([
                this.discoverTools(),
                this.discoverResources(),
                this.discoverPrompts()
            ]);
            
        } catch (error) {
            console.error('Error discovering capabilities:', error);
        }
    }

    async discoverTools() {
        try {
            const response = await this.sendSSERequest('tools/list', {});
            if (response.tools) {
                this.tools.clear();
                response.tools.forEach(tool => {
                    this.tools.set(tool.name, tool);
                });
                console.error(`Discovered ${this.tools.size} tools`);
            }
        } catch (error) {
            console.error('Error discovering tools:', error);
        }
    }

    async discoverResources() {
        try {
            const response = await this.sendSSERequest('resources/list', {});
            if (response.resources) {
                this.resources.clear();
                response.resources.forEach(resource => {
                    this.resources.set(resource.uri, resource);
                });
                console.error(`Discovered ${this.resources.size} resources`);
            }
        } catch (error) {
            console.error('Error discovering resources:', error);
        }
    }

    async discoverPrompts() {
        try {
            const response = await this.sendSSERequest('prompts/list', {});
            if (response.prompts) {
                this.prompts.clear();
                response.prompts.forEach(prompt => {
                    this.prompts.set(prompt.name, prompt);
                });
                console.error(`Discovered ${this.prompts.size} prompts`);
            }
        } catch (error) {
            console.error('Error discovering prompts:', error);
        }
    }

    setupHandlers() {
        // Tools handlers
        this.server.setRequestHandler('tools/list', async () => {
            return {
                tools: Array.from(this.tools.values())
            };
        });

        this.server.setRequestHandler('tools/call', async (request) => {
            const { name, arguments: args } = request.params;
            return await this.sendSSERequest('tools/call', { name, arguments: args });
        });

        // MCP spec defines ping as returning an empty result to confirm liveness.
        this.server.setRequestHandler('ping', async () => {
            return {};
        });

        // Resources handlers
        this.server.setRequestHandler('resources/list', async () => {
            return {
                resources: Array.from(this.resources.values())
            };
        });

        this.server.setRequestHandler('resources/read', async (request) => {
            const { uri } = request.params;
            return await this.sendSSERequest('resources/read', { uri });
        });

        this.server.setRequestHandler('resources/subscribe', async (request) => {
            const { uri } = request.params;
            return await this.sendSSERequest('resources/subscribe', { uri });
        });

        this.server.setRequestHandler('resources/unsubscribe', async (request) => {
            const { uri } = request.params;
            return await this.sendSSERequest('resources/unsubscribe', { uri });
        });

        // Prompts handlers
        this.server.setRequestHandler('prompts/list', async () => {
            return {
                prompts: Array.from(this.prompts.values())
            };
        });

        this.server.setRequestHandler('prompts/get', async (request) => {
            const { name, arguments: args } = request.params;
            return await this.sendSSERequest('prompts/get', { name, arguments: args });
        });

        // Completion handler
        this.server.setRequestHandler('completion/complete', async (request) => {
            return await this.sendSSERequest('completion/complete', request.params);
        });

        // Logging handler
        this.server.setRequestHandler('logging/setLevel', async (request) => {
            return await this.sendSSERequest('logging/setLevel', request.params);
        });
    }

    async run() {
        await this.initialize();
        
        // Start stdio transport
        const transport = new StdioServerTransport();
        await this.server.connect(transport);
        
        console.error('MCP SSE Bridge running...');
    }

    async shutdown() {
        if (this.eventSource) {
            this.eventSource.close();
        }
        
        // Reject all pending requests
        for (const [id, { reject }] of this.pendingRequests) {
            reject(new Error('Bridge shutting down'));
        }
        this.pendingRequests.clear();
    }
}

// Main execution
async function main() {
    const sseUrl = process.env.MCP_SSE_URL || 'http://127.0.0.1:9680/mcp';
    
    const bridge = new MCPSSEBridge(sseUrl);
    
    try {
        await bridge.run();
    } catch (error) {
        console.error('Bridge failed:', error);
        process.exit(1);
    }
}

// Handle graceful shutdown
process.on('SIGINT', async () => {
    console.error('Shutting down bridge...');
    if (global.bridge) {
        await global.bridge.shutdown();
    }
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.error('Shutting down bridge...');
    if (global.bridge) {
        await global.bridge.shutdown();
    }
    process.exit(0);
});

if (require.main === module) {
    main().catch(error => {
        console.error('Fatal error:', error);
        process.exit(1);
    });
}

module.exports = { MCPSSEBridge };
