import {
  ActivityEntry,
  Board,
  BoardComment,
  BoardItem,
  BoardState,
  CreateItemInput,
  Subtask,
  UpdateItemInput,
} from '../types.js';

/**
 * Command Board API client for services/command-board.
 *
 * Same-origin by default (empty base): in dev the Vite proxy forwards /api
 * to the service; in production the app is served on the same origin as
 * the API behind the Solorion login seam. Set VITE_BOARD_API_URL only for
 * non-standard deployments.
 */
export class BoardApiClient {
  private baseUrl: string;
  private actor: string;

  constructor(baseUrl?: string, actor = 'scotty') {
    this.baseUrl =
      baseUrl ||
      (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_BOARD_API_URL) ||
      '';
    this.actor = actor;
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  public setActor(actor: string): void {
    this.actor = actor;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Board-Actor': this.actor,
      ...((options.headers as Record<string, string>) || {}),
    };
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      let errorMsg = `HTTP ${res.status}: ${res.statusText}`;
      try {
        const errJson = await res.json();
        if (errJson.message) errorMsg = errJson.message;
        else if (errJson.error) errorMsg = errJson.error;
      } catch {
        // keep fallback
      }
      throw new Error(errorMsg);
    }
    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
  }

  // ---------- state ----------
  public async getState(activityLimit = 100): Promise<BoardState> {
    return this.request<BoardState>(`/api/v1/state?activityLimit=${activityLimit}`);
  }

  public async listActivity(limit = 100): Promise<ActivityEntry[]> {
    return this.request<ActivityEntry[]>(`/api/v1/activity?limit=${limit}`);
  }

  // ---------- boards ----------
  public async listBoards(): Promise<Board[]> {
    return this.request<Board[]>('/api/v1/boards');
  }

  public async createBoard(name: string): Promise<Board> {
    return this.request<Board>('/api/v1/boards', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  }

  public async deleteBoard(id: string): Promise<void> {
    return this.request<void>(`/api/v1/boards/${encodeURIComponent(id)}`, { method: 'DELETE' });
  }

  // ---------- items ----------
  public async createItem(input: CreateItemInput): Promise<BoardItem> {
    return this.request<BoardItem>('/api/v1/items', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  }

  public async updateItem(id: string, patch: UpdateItemInput): Promise<BoardItem> {
    return this.request<BoardItem>(`/api/v1/items/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  }

  public async deleteItem(id: string): Promise<void> {
    return this.request<void>(`/api/v1/items/${encodeURIComponent(id)}`, { method: 'DELETE' });
  }

  public async cooperUpdate(
    id: string,
    patch: UpdateItemInput & { comment?: string; activityText?: string }
  ): Promise<BoardItem> {
    return this.request<BoardItem>(`/api/v1/items/${encodeURIComponent(id)}/cooper-update`, {
      method: 'POST',
      body: JSON.stringify(patch),
    });
  }

  // ---------- comments & subtasks ----------
  public async addComment(itemId: string, author: string, body: string): Promise<BoardComment> {
    return this.request<BoardComment>(`/api/v1/items/${encodeURIComponent(itemId)}/comments`, {
      method: 'POST',
      body: JSON.stringify({ author, body }),
    });
  }

  public async addSubtask(itemId: string, title: string): Promise<Subtask> {
    return this.request<Subtask>(`/api/v1/items/${encodeURIComponent(itemId)}/subtasks`, {
      method: 'POST',
      body: JSON.stringify({ title }),
    });
  }

  public async updateSubtask(id: string, patch: { title?: string; checked?: boolean }): Promise<Subtask> {
    return this.request<Subtask>(`/api/v1/subtasks/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  }

  public async deleteSubtask(id: string): Promise<void> {
    return this.request<void>(`/api/v1/subtasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
  }
}

export const api = new BoardApiClient();
