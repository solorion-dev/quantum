import fastify, { FastifyInstance } from 'fastify';
import { fileURLToPath } from 'node:url';
import { openDatabase } from './db.js';
import { seedIfEmpty } from './seed.js';
import { BoardService } from './service.js';
import { registerRestRoutes } from './rest.js';
import { HealthResponse } from './types.js';

export interface ServerOptions {
  dbPath?: string;
  token?: string;
  port?: number;
  host?: string;
  logger?: boolean;
}

export interface ServerInstance {
  app: FastifyInstance;
  service: BoardService;
  start: () => Promise<string>;
  close: () => Promise<void>;
}

export async function createServer(options: ServerOptions = {}): Promise<ServerInstance> {
  const db = openDatabase(options.dbPath);
  seedIfEmpty(db);
  const service = new BoardService(db);

  const app = fastify({ logger: options.logger ?? false });

  // Support empty JSON bodies gracefully on POST/PATCH/DELETE
  app.addContentTypeParser('application/json', { parseAs: 'string' }, (_req, body: string, done) => {
    if (!body || body.trim() === '') {
      done(null, {});
      return;
    }
    try {
      done(null, JSON.parse(body));
    } catch (err: any) {
      err.statusCode = 400;
      done(err, undefined);
    }
  });

  app.setErrorHandler((error: any, _req, reply) => {
    if (error.statusCode === 400 || error instanceof SyntaxError || (error as any).status === 400) {
      reply.status(400).send({ error: 'Bad Request', message: error.message || 'Malformed or invalid JSON body' });
      return;
    }
    const statusCode = error.statusCode || 500;
    reply.status(statusCode).send({
      error: error.name || 'Internal Server Error',
      message: error.message || 'An unexpected error occurred',
    });
  });

  app.setNotFoundHandler((req, reply) => {
    reply.status(404).send({ error: 'Not Found', message: `Route ${req.method} ${req.url} not found` });
  });

  // CORS for the web app (dev origin + same-origin deploys)
  app.addHook('onRequest', async (req, reply) => {
    reply.header('Access-Control-Allow-Origin', '*');
    reply.header('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS');
    reply.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Board-Actor');
    if (req.method === 'OPTIONS') {
      reply.status(204).send();
      return reply;
    }
  });

  // Optional Bearer token on /api/* (set BOARD_TOKEN in production; the
  // Solorion-login seam fronts this service — see apps/command-board README).
  app.addHook('onRequest', async (req, reply) => {
    const configuredToken = options.token ?? process.env.BOARD_TOKEN;
    if (!configuredToken) return;
    const pathWithoutQuery = req.url.split('?')[0];
    if (!pathWithoutQuery.startsWith('/api/')) return;
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      reply.status(401).send({ error: 'Unauthorized: missing Bearer token' });
      return reply;
    }
    if (authHeader.slice(7).trim() !== configuredToken) {
      reply.status(401).send({ error: 'Unauthorized: invalid Bearer token' });
      return reply;
    }
  });

  app.get('/health', async (): Promise<HealthResponse> => {
    const counts = service.getCounts();
    return { status: 'ok', schema_version: service.getSchemaVersion(), boards: counts.boards, items: counts.items };
  });

  registerRestRoutes(app, service);

  const port = options.port ?? (process.env.PORT ? parseInt(process.env.PORT, 10) : 8798);
  const host = options.host ?? (process.env.HOST || '127.0.0.1');

  return {
    app,
    service,
    start: async () => {
      const address = await app.listen({ port, host });
      return address;
    },
    close: async () => {
      await app.close();
      db.close();
    },
  };
}

// Auto-start if executed directly
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  createServer({ logger: true })
    .then(async (server) => {
      const address = await server.start();
      console.log(`Quantum Command Board service running at ${address}`);
      const shutdown = async (signal: string) => {
        console.log(`Received ${signal}, shutting down gracefully...`);
        try {
          await server.close();
          console.log('Command Board service closed cleanly');
          process.exit(0);
        } catch (err) {
          console.error('Error during shutdown:', err);
          process.exit(1);
        }
      };
      process.on('SIGINT', () => shutdown('SIGINT'));
      process.on('SIGTERM', () => shutdown('SIGTERM'));
    })
    .catch((err) => {
      console.error('Fatal error starting Command Board service:', err);
      process.exit(1);
    });
}
