import { Container } from "@cloudflare/containers";

// Secrets : `wrangler secret put <NOM>` (jamais dans le code ni dans wrangler.jsonc).
const SECRETS = [
  "RODIUM_API_KEY", "TAVILY_API_KEY", "OPENWEATHER_API_KEY", "NOTION_TOKEN", "NOTION_PARENT_PAGE_ID",
  "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "GOOGLE_CALENDAR_ID", "GOOGLE_DRIVE_FOLDER_ID",
  "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "APP_ACCESS_CODE",
] as const;

type Env = { AGENT: DurableObjectNamespace<AgentContainer> } & Partial<Record<(typeof SECRETS)[number], string>>;

export class AgentContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "2h"; // les conversations vivent en mémoire du conteneur

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.envVars = Object.fromEntries(SECRETS.filter((k) => env[k]).map((k) => [k, env[k] as string]));
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Une seule instance : toutes les sessions de chat partagent le même processus.
    return env.AGENT.getByName("main").fetch(request);
  },
};
