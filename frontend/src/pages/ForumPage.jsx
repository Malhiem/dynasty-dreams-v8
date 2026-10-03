/**
 * Iter 217 — Forum page.
 *
 * League-scoped threaded discussion. Pulls the active league via
 * useActiveLeague(), renders threads + posts with a reply form +
 * Report button per post (uses iter 205 user-reports endpoint).
 */
import { useEffect, useState, useCallback } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Pin, Lock, ArrowLeft, MessageSquare } from "lucide-react";
import ReportUserButton from "@/components/ReportUserButton";

export default function ForumPage() {
  const { leagueId, league } = useActiveLeague();
  const [threads, setThreads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedThread, setSelectedThread] = useState(null);

  const loadThreads = useCallback(async () => {
    if (!leagueId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/forum/threads?league_id=${leagueId}&limit=50`);
      setThreads(data.threads || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load forum");
    } finally {
      setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => { loadThreads(); }, [loadThreads]);

  if (!leagueId) {
    return (
      <AppLayout>
        <div className="p-8 max-w-2xl">
          <h1 className="text-2xl font-bold">Forum</h1>
          <p className="text-muted-foreground mt-2">Select a league to view the forum.</p>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="p-6 max-w-5xl" data-testid="forum-page">
        {selectedThread ? (
          <ThreadView
            thread={selectedThread}
            onBack={() => { setSelectedThread(null); loadThreads(); }}
          />
        ) : (
          <ThreadList
            threads={threads}
            loading={loading}
            leagueName={league?.name}
            leagueId={leagueId}
            onSelect={setSelectedThread}
            onCreate={loadThreads}
          />
        )}
      </div>
    </AppLayout>
  );
}

function ThreadList({ threads, loading, leagueName, leagueId, onSelect, onCreate }) {
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!title.trim() || !body.trim()) {
      toast.error("Title and body required");
      return;
    }
    setBusy(true);
    try {
      await api.post("/forum/threads", { league_id: leagueId, title: title.trim(), body: body.trim() });
      toast.success("Thread posted");
      setTitle(""); setBody(""); setCreating(false);
      onCreate?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create thread");
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" data-testid="forum-title">
            <MessageSquare className="h-6 w-6 text-primary" />
            Forum
          </h1>
          <p className="text-muted-foreground text-sm">{leagueName || "League"} · {threads.length} threads</p>
        </div>
        <Button onClick={() => setCreating(!creating)} data-testid="forum-new-thread-btn">
          {creating ? "Cancel" : "New thread"}
        </Button>
      </div>

      {creating && (
        <Card data-testid="forum-new-thread-form">
          <CardHeader>
            <CardTitle className="text-base">Start a new thread</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              placeholder="Thread title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              data-testid="forum-thread-title-input"
            />
            <Textarea
              placeholder="What's on your mind?"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              data-testid="forum-thread-body-input"
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setCreating(false)}>Cancel</Button>
              <Button onClick={submit} disabled={busy} data-testid="forum-thread-submit-btn">
                {busy ? "Posting…" : "Post thread"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {!loading && threads.length === 0 && !creating && (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            No threads yet — start the first one!
          </CardContent>
        </Card>
      )}

      <ul className="space-y-2" data-testid="forum-thread-list">
        {threads.map((t) => (
          <li key={t.id}>
            <button
              type="button"
              onClick={() => onSelect(t)}
              className="w-full text-left rounded-lg border border-border bg-card hover:bg-secondary/40 transition-colors p-4 flex items-start gap-3"
              data-testid={`forum-thread-${t.id}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {t.pinned && <Pin className="h-3.5 w-3.5 text-amber-300" />}
                  {t.locked && <Lock className="h-3.5 w-3.5 text-muted-foreground" />}
                  <span className="font-medium truncate">{t.title}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  by {t.author_email} · {t.post_count} post{t.post_count === 1 ? "" : "s"}
                  · last activity {t.last_post_at ? new Date(t.last_post_at).toLocaleString() : "—"}
                </p>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ThreadView({ thread, onBack }) {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/forum/threads/${thread.id}/posts`);
      setPosts(data.posts || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load posts");
    } finally { setLoading(false); }
  }, [thread.id]);

  useEffect(() => { load(); }, [load]);

  const submitReply = async () => {
    if (!reply.trim()) return;
    setBusy(true);
    try {
      await api.post(`/forum/threads/${thread.id}/posts`, { body: reply.trim() });
      setReply("");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Reply failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4" data-testid="forum-thread-view">
      <Button variant="outline" size="sm" onClick={onBack} data-testid="forum-back-btn">
        <ArrowLeft className="h-4 w-4 mr-1" /> Back to threads
      </Button>

      <Card>
        <CardHeader>
          <CardTitle data-testid="forum-thread-view-title">{thread.title}</CardTitle>
          <CardDescription>
            by {thread.author_email} · started {thread.created_at ? new Date(thread.created_at).toLocaleString() : "—"}
            {thread.locked && <span className="ml-2 text-amber-300">· locked</span>}
          </CardDescription>
        </CardHeader>
      </Card>

      {loading && <p className="text-sm text-muted-foreground">Loading posts…</p>}
      <ul className="space-y-2" data-testid="forum-post-list">
        {posts.map((p) => (
          <li key={p.id}>
            <Card className="border-border">
              <CardContent className="py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm whitespace-pre-wrap ${p.deleted_at ? "italic text-muted-foreground" : ""}`}>
                      {p.body}
                    </p>
                    <p className="text-xs text-muted-foreground mt-2">
                      {p.author_email} · {p.created_at ? new Date(p.created_at).toLocaleString() : "—"}
                    </p>
                  </div>
                  {!p.deleted_at && (
                    <ReportUserButton
                      targetUserId={p.author_id}
                      targetUserEmail={p.author_email}
                      leagueId={thread.league_id}
                      contextUrl={`forum/post/${p.id}`}
                      variant="icon"
                    />
                  )}
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>

      {!thread.locked && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Reply</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Textarea
              placeholder="Write a reply…"
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              rows={3}
              data-testid="forum-reply-input"
            />
            <div className="flex justify-end">
              <Button onClick={submitReply} disabled={busy || !reply.trim()} data-testid="forum-reply-submit-btn">
                {busy ? "Posting…" : "Post reply"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
