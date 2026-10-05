"""外部發佈全部使用 HTTP stub；驗證實際資料庫、人工確認與 worker 恢復邊界。"""

import json
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.models import BrandProfile, Comment, Post, PublishChannel, SocialAccount, Task, Tenant, UsageLedger, User, Video, new_id, utcnow
from app.security import encrypt_secret
from app.services import comments, posts, renderer
from app.services.upload_post import UploadPost
from app.worker import HANDLERS, Worker

BASE = "https://api.upload-post.com/api"
KEY = "test-publishing-key-abcd"


def remote(*, platform="instagram", identifier="account-123", **changes):
    return {"success": True, "profiles": [{"username": "factory", "social_accounts": {platform: {
        "username": identifier, "display_name": "Test Factory", "handle": "testfactory", "capabilities": ["comments"], **changes}}}]}


def setup(db, platform="instagram"):
    user = db.scalars(select(User).where(User.email == "admin@example.com")).one()
    profile = BrandProfile(id=new_id(), tenant_id=user.tenant_id, name="Test Factory")
    channel = PublishChannel(id=new_id(), tenant_id=user.tenant_id, name="Test Upload-Post", base_url=BASE,
        api_key_encrypted=encrypt_secret(KEY), api_key_last4="abcd")
    db.add_all([profile, channel]); db.flush()
    account = SocialAccount(id=new_id(), tenant_id=user.tenant_id, channel_id=channel.id, profile_id=profile.id,
        remote_profile="factory", platform=platform, external_account_id="account-123", display_name="Test Factory",
        auth_status="connected", capabilities=["comments"])
    video = Video(id=new_id(), tenant_id=user.tenant_id, profile_id=profile.id, batch_id=new_id(), title="Test Video",
        status="approved", has_output=True, reviewed_by=user.id, reviewed_at=utcnow(), rendered_at=utcnow())
    db.add_all([account, video]); db.commit()
    directory = renderer.video_dir(user.tenant_id, video.id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "final.mp4").write_bytes(b"synthetic-approved-video")
    body = {"request_key": new_id(), "video_id": video.id, "account_id": account.id, "title": "Factory story",
        "description": "Meet our team", "hashtags": ["#factory"], "schedule_at": (utcnow() - timedelta(seconds=1)).isoformat(),
        "confirmed": True, "is_ai_generated": True}
    return user, profile, channel, account, video, body


def schedule(admin, body):
    r = admin.post("/api/posts", json=body)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def published(db, admin, *, platform="instagram"):
    values = setup(db, platform)
    data = schedule(admin, values[-1])
    post = db.get(Post, data["id"])
    post.status, post.remote_id, post.url = "published", "post-123", "https://www.instagram.com/p/test/"
    post.published_at, post.next_comment_sync_at = utcnow(), utcnow()
    db.commit()
    return values, post


@respx.mock
def test_account_binding_uses_verified_identifiers_and_sanitizes_remote_payload(admin, db):
    user, profile, channel, *_ = setup(db)
    data = remote(platform="youtube", access_token=KEY, cookies="must-not-return")
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=data))
    r = admin.get("/api/social-accounts/remote-profiles", params={"channel_id": channel.id})
    assert r.status_code == 200 and KEY not in r.text and "cookies" not in r.text
    body = {"channel_id": channel.id, "profile_id": profile.id, "remote_profile": "factory", "platforms": ["youtube"]}
    r = admin.post("/api/social-accounts/bind", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["data"][0]["external_account_id"] == "account-123"
    assert admin.post("/api/social-accounts/bind", json=body).status_code == 200
    assert db.scalar(select(func.count()).select_from(SocialAccount).where(SocialAccount.platform == "youtube")) == 1


@respx.mock
@pytest.mark.parametrize("details,status", [(remote(reauth_required=True), "reauth_required"), (remote(identifier="changed"), "destination_changed"), ({"success": True, "profiles": []}, "disconnected")])
def test_authorization_refresh_reports_real_status(admin, db, details, status):
    *_, account, video, body = setup(db)
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=details))
    r = admin.post(f"/api/social-accounts/{account.id}/check")
    assert r.status_code == 200 and r.json()["data"]["auth_status"] == status


@respx.mock
def test_missing_identifier_does_not_count_as_connected(admin, db):
    user, profile, channel, *_ = setup(db)
    data = remote(identifier="", display_name="Looks connected")
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=data))
    r = admin.post("/api/social-accounts/bind", json={"channel_id": channel.id, "profile_id": profile.id, "remote_profile": "factory", "platforms": ["instagram"]})
    assert r.status_code == 409


def test_scheduling_requires_human_confirmation_and_matching_profile(admin, db):
    user, profile, channel, account, video, body = setup(db)
    unconfirmed = dict(body); unconfirmed.pop("confirmed")
    assert admin.post("/api/posts", json=unconfirmed).status_code == 422
    assert admin.post("/api/posts", json={**body, "confirmed": False}).status_code == 422
    video.status = "pending_review"; db.commit()
    assert admin.post("/api/posts", json=body).json()["reason"] == "video_not_approved"
    video.status = "approved"; video.profile_id = None; db.commit()
    assert admin.post("/api/posts", json=body).json()["reason"] == "profile_mismatch"
    assert db.scalar(select(func.count()).select_from(Post)) == 0


@pytest.mark.parametrize("changes,reason", [({"schedule_at": "2026-12-01T12:00:00"}, "timezone_required"), ({"schedule_at": "2020-01-01T12:00:00Z"}, "invalid_schedule"), ({"title": "x" * 100, "description": "x" * 2000, "hashtags": ["#" + "h" * 49] * 10}, "caption_too_long")])
def test_schedule_validation(admin, db, changes, reason):
    *_, body = setup(db)
    r = admin.post("/api/posts", json={**body, **changes})
    assert r.status_code == 400 and r.json()["reason"] == reason


def test_duplicate_request_deduplicates_and_changed_payload_conflicts(admin, db):
    *_, body = setup(db)
    first = schedule(admin, body)
    assert schedule(admin, body)["id"] == first["id"]
    assert admin.post("/api/posts", json={**body, "title": "Changed"}).status_code == 409
    assert db.scalar(select(func.count()).select_from(Post)) == 1
    assert db.scalar(select(func.count()).select_from(Task)) == 1


def test_future_schedule_and_cancel_do_not_publish(admin, db):
    *_, body = setup(db)
    data = schedule(admin, {**body, "schedule_at": (utcnow() + timedelta(hours=1)).isoformat()})
    assert Worker(1).run_one(db) is False
    assert admin.post(f"/api/posts/{data['id']}/cancel").json()["data"]["status"] == "canceled"
    assert db.scalar(select(func.count()).select_from(UsageLedger)) == 0


def test_active_schedule_blocks_rerender_reject_delete_and_failed_render_retry(admin, db):
    user, profile, channel, account, video, body = setup(db)
    schedule(admin, body)
    for path, payload in [(f"/api/videos/{video.id}/rerender", {"reshuffle": False}), (f"/api/videos/{video.id}/review", {"action": "reject", "note": "Change needed"})]:
        assert admin.post(path, json=payload).json()["reason"] == "video_scheduled"
    assert admin.delete(f"/api/videos/{video.id}").status_code == 409
    task = Task(type="video.render", tenant_id=user.tenant_id, payload={"video_id": video.id}, status="failed")
    db.add(task); db.commit()
    assert admin.post(f"/api/tasks/{task.id}/retry").json()["reason"] == "video_scheduled"


@respx.mock
def test_worker_publishes_once_with_idempotency_and_records_unknown_cost(admin, db):
    *_, body = setup(db)
    data = schedule(admin, body)
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote()))
    route = respx.post(BASE + "/upload").mock(return_value=httpx.Response(200, json={"success": True, "results": {"instagram": {"success": True, "url": "https://www.instagram.com/p/test/", "post_id": "post-123"}}}))
    assert Worker(1).run_one(db)
    post = db.get(Post, data["id"])
    assert post.status == "published" and post.remote_id == "post-123"
    request = route.calls.last.request
    assert request.headers["Idempotency-Key"] == post.id
    assert request.headers["Authorization"] == "Apikey " + KEY
    assert post.id.encode() in request.content and b'name="platform[]"' in request.content
    assert b'name="is_ai_generated"' in request.content and b"synthetic-approved-video" in request.content
    entry = db.scalars(select(UsageLedger).where(UsageLedger.post_id == post.id)).one()
    assert entry.status == "succeeded" and entry.cost_micros is None
    task = db.scalars(select(Task).where(Task.type == "publish.post")).one()
    assert posts.publish_task(db, task) == {"skipped": "published"}
    assert route.call_count == 1


@respx.mock
@pytest.mark.parametrize("failure", ["timeout", "server_error", "invalid_json", "unexpected_request"])
def test_uncertain_publish_only_reconciles_original_request(admin, db, failure):
    *_, body = setup(db)
    data = schedule(admin, body)
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote()))
    route = respx.post(BASE + "/upload")
    if failure == "timeout": route.mock(side_effect=httpx.ReadTimeout("sensitive " + KEY))
    elif failure == "server_error": route.mock(return_value=httpx.Response(503, text=KEY))
    elif failure == "invalid_json": route.mock(return_value=httpx.Response(200, text=KEY))
    else: route.mock(return_value=httpx.Response(200, json={"success": True, "request_id": "wrong-id"}))
    assert Worker(1).run_one(db)
    post = db.get(Post, data["id"])
    assert post.status == "uncertain" and KEY not in post.error
    status = respx.get(BASE + "/uploadposts/status").mock(return_value=httpx.Response(200, json={"request_id": post.id, "status": "completed", "results": [{"platform": "instagram", "success": True, "post_id": "post-123", "url": "https://www.instagram.com/p/test/"}]}))
    r = admin.post(f"/api/posts/{post.id}/reconcile")
    assert r.status_code == 200 and r.json()["data"]["status"] == "published"
    assert route.call_count == 1 and status.calls.last.request.url.params["request_id"] == post.id
    db.refresh(post)
    assert admin.post(f"/api/posts/{post.id}/cancel").status_code == 409
    assert db.scalars(select(UsageLedger).where(UsageLedger.post_id == post.id)).one().cost_micros is None


@respx.mock
def test_crash_after_submission_boundary_restores_with_get_only(admin, db, monkeypatch):
    *_, body = setup(db)
    data = schedule(admin, body)
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote()))
    route = respx.post(BASE + "/upload").mock(return_value=httpx.Response(200, json={"success": True, "request_id": data["id"]}))
    real_request = UploadPost.request
    def crash_after_response(provider, method, path, **kwargs):
        result = real_request(provider, method, path, **kwargs)
        if method == "POST":
            raise SystemExit("simulated worker crash after provider accepted")
        return result
    monkeypatch.setattr(UploadPost, "request", crash_after_response)
    task = db.scalars(select(Task).where(Task.type == "publish.post")).one()
    with pytest.raises(SystemExit): posts.publish_task(db, task)
    post = db.get(Post, data["id"])
    assert post.status == "submitting"
    respx.get(BASE + "/uploadposts/status").mock(return_value=httpx.Response(200, json={"request_id": post.id, "status": "completed", "results": [{"platform": "instagram", "success": True, "post_id": "post-123"}]}))
    assert posts.publish_task(db, task)["status"] == "published"
    assert route.call_count == 1


@respx.mock
def test_definite_rate_rejection_retries_same_request_without_false_success(admin, db):
    *_, body = setup(db)
    data = schedule(admin, body)
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote()))
    route = respx.post(BASE + "/upload").mock(return_value=httpx.Response(429, json={"success": False, "message": KEY}))
    Worker(1).run_one(db)
    task = db.scalars(select(Task).where(Task.type == "publish.post")).one()
    assert task.status == "queued" and task.attempts == 1
    assert db.get(Post, data["id"]).status == "queued"
    assert db.scalars(select(UsageLedger)).one().status == "failed"
    task.run_after = utcnow(); db.commit()
    route.mock(return_value=httpx.Response(200, json={"success": True, "request_id": data["id"]}))
    Worker(1).run_one(db)
    assert db.get(Post, data["id"]).status == "processing"
    assert route.call_count == 2
    assert {c.request.headers["Idempotency-Key"] for c in route.calls} == {data["id"]}


@respx.mock
@pytest.mark.parametrize("change", ["video_hash", "video_review", "remote_account", "disabled_account"])
def test_worker_rechecks_review_and_destination_before_any_post(admin, db, change):
    user, profile, channel, account, video, body = setup(db)
    data = schedule(admin, body)
    if change == "video_hash": (renderer.video_dir(user.tenant_id, video.id) / "final.mp4").write_bytes(b"unapproved-replacement")
    if change == "video_review": video.reviewed_at = utcnow()
    if change == "disabled_account": account.enabled = False
    db.commit()
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote(identifier="changed" if change == "remote_account" else "account-123")))
    route = respx.post(BASE + "/upload").mock(return_value=httpx.Response(200, json={"success": True}))
    Worker(1).run_one(db)
    assert db.get(Post, data["id"]).status == "failed" and route.call_count == 0


@respx.mock
@pytest.mark.parametrize("result,status", [({"success": True, "fallback_to_inbox": True}, "draft_delivery"), ({"success": True, "skipped": True}, "failed"), ({"success": True, "url": "javascript:bad"}, "uncertain")])
def test_non_public_and_skipped_receipts_are_not_published(admin, db, result, status):
    *_, body = setup(db, "tiktok")
    data = schedule(admin, body)
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote(platform="tiktok")))
    respx.post(BASE + "/upload").mock(return_value=httpx.Response(200, json={"success": True, "results": {"tiktok": result}}))
    Worker(1).run_one(db)
    assert db.get(Post, data["id"]).status == status


@respx.mock
def test_comment_pagination_deduplication_and_edit_invalidate_old_suggestion(admin, db):
    values, post = published(db, admin)
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote()))
    route = respx.get(BASE + "/uploadposts/comments").mock(side_effect=[
        httpx.Response(200, json={"success": True, "comments": [{"id": "c1", "text": "Price?", "user": {"username": "buyer"}}], "pagination": {"has_next": True, "next_cursor": "next"}}),
        httpx.Response(200, json={"success": True, "comments": [{"id": "c2", "message": "Bad service", "from": {"name": "Buyer 2"}}]}),
    ])
    r = admin.post(f"/api/posts/{post.id}/sync-comments")
    assert r.status_code == 200 and r.json()["data"]["comments"] == 2
    assert route.calls[1].request.url.params["after"] == "next"
    comment = db.scalars(select(Comment).where(Comment.remote_id == "c1")).one()
    old = comments.version(comment)
    comment.suggested_reply, comment.intent = "Old suggestion", "enquiry"; db.commit()
    route.mock(return_value=httpx.Response(200, json={"success": True, "comments": [{"id": "c1", "text": "Changed question"}]}))
    assert admin.post(f"/api/posts/{post.id}/sync-comments").status_code == 200
    db.refresh(comment)
    assert comment.suggested_reply == "" and comments.version(comment) != old
    assert db.scalar(select(func.count()).select_from(Comment)) == 2
    assert admin.post(f"/api/comments/{comment.id}/reply", json={"text": "Reply", "version": old, "confirmed": True}).status_code == 409


@respx.mock
def test_comment_sync_error_is_persisted_without_erasing_existing_comments(admin, db):
    values, post = published(db, admin)
    comment = Comment(tenant_id=post.tenant_id, post_id=post.id, remote_id="keep", text="Keep me")
    db.add(comment); db.commit()
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote()))
    respx.get(BASE + "/uploadposts/comments").mock(return_value=httpx.Response(200, json={"success": False, "error": KEY}))
    r = admin.post(f"/api/posts/{post.id}/sync-comments")
    assert r.status_code == 502 and KEY not in r.text
    db.refresh(post)
    assert post.comments_error and post.comments_checked_at is None
    assert db.get(Comment, comment.id).text == "Keep me"


@respx.mock
def test_tiktok_comments_require_connection_capability(admin, db):
    values, post = published(db, admin, platform="tiktok")
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote(platform="tiktok", capabilities=[])))
    assert admin.post(f"/api/posts/{post.id}/sync-comments").json()["reason"] == "comments_not_supported"


@respx.mock
def test_ai_suggestion_is_not_sent_and_negative_filter_uses_saved_intent(admin, db, monkeypatch):
    values, post = published(db, admin)
    comment = Comment(tenant_id=post.tenant_id, post_id=post.id, remote_id="c1", text="Bad service")
    db.add(comment); db.commit()
    monkeypatch.setattr("app.services.ai_provider.default_model", lambda *_: object())
    calls = []
    def chat(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=json.dumps({"intent": "complaint", "reply": "Please share the order details."}))
    monkeypatch.setattr("app.services.ai_provider.chat", chat)
    r = admin.post(f"/api/comments/{comment.id}/suggest")
    assert r.status_code == 200 and r.json()["data"]["reply_status"] == "unreplied"
    assert calls[0]["source"] == "comment_suggest" and len(respx.calls) == 0
    assert admin.get("/api/comments", params={"negative": True, "unreplied": True}).json()["data"]["total"] == 1


@respx.mock
def test_reply_requires_confirmation_preserves_receipt_and_prevents_double_send(admin, db):
    values, post = published(db, admin, platform="tiktok")
    comment = Comment(tenant_id=post.tenant_id, post_id=post.id, remote_id="c1", text="Price?")
    db.add(comment); db.commit()
    body = {"text": "Please send your specifications", "version": comments.version(comment), "confirmed": True}
    assert admin.post(f"/api/comments/{comment.id}/reply", json={**body, "confirmed": False}).status_code == 422
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote(platform="tiktok")))
    route = respx.post(BASE + "/uploadposts/comments/create").mock(return_value=httpx.Response(200, json={"success": True, "result": {"comment_id": "reply-123"}}))
    r = admin.post(f"/api/comments/{comment.id}/reply", json=body)
    assert r.status_code == 200 and r.json()["data"]["remote_reply_id"] == "reply-123"
    sent = json.loads(route.calls.last.request.content)
    assert sent["comment_id"] == "c1" and sent["post_id"] == post.remote_id and sent["message"] == body["text"]
    assert admin.post(f"/api/comments/{comment.id}/reply", json=body).status_code == 409
    assert route.call_count == 1
    entry = db.scalars(select(UsageLedger).where(UsageLedger.comment_id == comment.id)).one()
    assert entry.cost_micros is None and entry.status == "succeeded" and entry.user_id == values[0].id


@respx.mock
def test_reply_timeout_is_durable_uncertain_and_cannot_be_retried(admin, db):
    values, post = published(db, admin)
    comment = Comment(tenant_id=post.tenant_id, post_id=post.id, remote_id="c1", text="Price?")
    db.add(comment); db.commit()
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote()))
    route = respx.post(BASE + "/uploadposts/comments/create").mock(side_effect=httpx.ReadTimeout(KEY))
    body = {"text": "Thanks", "version": comments.version(comment), "confirmed": True}
    r = admin.post(f"/api/comments/{comment.id}/reply", json=body)
    assert r.status_code == 502 and KEY not in r.text
    db.refresh(comment)
    assert comment.reply_status == "uncertain" and comment.reply_text == "Thanks"
    assert admin.post(f"/api/comments/{comment.id}/reply", json=body).status_code == 409 and route.call_count == 1
    usage = admin.get("/api/usage", params={"status": "uncertain"}).json()["data"]
    assert usage["total"] == 1 and usage["items"][0]["cost_usd"] is None


def test_periodic_sync_deduplicates_and_worker_handlers_registered(admin, db):
    values, post = published(db, admin)
    comments.schedule_sync(db)
    post.next_comment_sync_at = utcnow(); db.commit()
    comments.schedule_sync(db)
    assert db.scalar(select(func.count()).select_from(Task).where(Task.type == "comment.sync")) == 1
    assert {"publish.post", "publish.reconcile", "comment.sync"} <= HANDLERS.keys()


@respx.mock
def test_publish_copy_is_validated_and_uses_ai_entry_without_posting(admin, db, monkeypatch):
    values = setup(db)
    monkeypatch.setattr("app.services.ai_provider.default_model", lambda *_: object())
    seen = []
    def chat(*args, **kwargs):
        seen.append(kwargs["source"])
        return SimpleNamespace(content=json.dumps({"title": "Factory", "description": "Meet us", "hashtags": ["#factory"]}))
    monkeypatch.setattr("app.services.ai_provider.chat", chat)
    r = admin.post("/api/posts/copy", json={"video_id": values[4].id, "platform": "youtube"})
    assert r.status_code == 200 and seen == ["post_copy"] and len(respx.calls) == 0
    assert db.scalar(select(func.count()).select_from(Post)) == 0


def test_all_publishing_objects_are_tenant_scoped_and_admin_only(admin, db):
    values, post = published(db, admin)
    tenant = Tenant(id=new_id(), name="Other factory"); db.add(tenant); db.flush()
    foreign = PublishChannel(id=new_id(), tenant_id=tenant.id, name="Other channel", base_url=BASE)
    foreign_account = SocialAccount(id=new_id(), tenant_id=tenant.id, channel_id=foreign.id, remote_profile="other", platform="instagram", external_account_id="other")
    db.add(foreign); db.flush(); db.add(foreign_account); db.commit()
    assert admin.get("/api/social-accounts/remote-profiles", params={"channel_id": foreign.id}).status_code == 404
    assert admin.post(f"/api/social-accounts/{foreign_account.id}/check").status_code == 404
    assert len(admin.get("/api/social-accounts").json()["data"]) == 1
    r = admin.post("/api/users", json={"email": "shooter@example.com", "display_name": "Shooter", "password": "valid-password-123", "role": "shooter"})
    assert r.status_code == 200
    admin.post("/api/auth/logout")
    admin.post("/api/auth/login", json={"email": "shooter@example.com", "password": "valid-password-123"})
    for path in ("/api/social-accounts", "/api/posts", "/api/comments"):
        assert admin.get(path).status_code == 403


def test_different_client_keys_cannot_repeat_same_video_on_same_account(admin, db):
    *_, body = setup(db)
    schedule(admin, body)
    r = admin.post("/api/posts", json={**body, "request_key": new_id()})
    assert r.status_code == 409 and r.json()["reason"] == "post_exists"


@respx.mock
def test_optional_auto_suggestion_uses_real_ai_ledger_without_sending_reply(admin, db):
    values, post = published(db, admin)
    user, profile, channel, account, *_ = values
    assert account.auto_suggest_enabled is False
    assert admin.post("/api/channels", json={"provider": "deepseek", "api_key": "sk-test-1234567890abcd"}).status_code == 200
    r = admin.patch(f"/api/social-accounts/{account.id}", json={"auto_suggest_enabled": True})
    assert r.status_code == 200 and r.json()["data"]["auto_suggest_enabled"] is True
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote()))
    respx.get(BASE + "/uploadposts/comments").mock(return_value=httpx.Response(200, json={"success": True, "comments": [{"id": "c1", "text": "Price?"}]}))
    assert admin.post(f"/api/posts/{post.id}/sync-comments").status_code == 200
    assert admin.post(f"/api/posts/{post.id}/sync-comments").status_code == 200
    comment = db.scalars(select(Comment)).one()
    assert db.scalar(select(func.count()).select_from(Task).where(Task.type == "comment.suggest")) == 1
    ai = respx.post("https://api.deepseek.com/chat/completions").mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps({"intent": "enquiry", "reply": "Please share your specifications."})}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}))
    task = db.scalars(select(Task).where(Task.type == "comment.suggest")).one()
    assert comments.suggest_task(db, task)["suggested"] is True
    db.refresh(comment)
    assert comment.ai_status == "ready" and comment.reply_status == "unreplied"
    entry = db.scalars(select(UsageLedger).where(UsageLedger.source == "comment_suggest")).one()
    assert entry.action == "ai.chat" and entry.input_tokens == 1000 and entry.user_id == user.id
    assert ai.call_count == 1 and not any("comments/create" in str(c.request.url) for c in respx.calls)


@respx.mock
def test_disabling_auto_suggestion_skips_queued_paid_call(admin, db, monkeypatch):
    values, post = published(db, admin)
    account = values[3]
    comment = Comment(id=new_id(), tenant_id=post.tenant_id, post_id=post.id, remote_id="c1", text="Price?", ai_status="pending")
    db.add(comment); db.commit()
    task = Task(type="comment.suggest", tenant_id=post.tenant_id, payload={"comment_id": comment.id, "version": comments.version(comment)})
    db.add(task); db.commit()
    assert comments.suggest_task(db, task)["skipped"] == "auto_suggest_disabled"
    assert db.scalar(select(func.count()).select_from(UsageLedger)) == 0 and len(respx.calls) == 0


@respx.mock
def test_ai_crash_boundary_does_not_repeat_paid_generation(admin, db, monkeypatch):
    values, post = published(db, admin)
    user, profile, channel, account, *_ = values
    account.auto_suggest_enabled, account.auto_suggest_by = True, user.id
    comment = Comment(id=new_id(), tenant_id=post.tenant_id, post_id=post.id, remote_id="c1", text="Price?", ai_status="pending")
    db.add(comment); db.commit()
    task = Task(type="comment.suggest", tenant_id=post.tenant_id, payload={"comment_id": comment.id, "version": comments.version(comment)})
    db.add(task); db.commit()
    monkeypatch.setattr("app.services.ai_provider.default_model", lambda *_: object())
    seen = []
    def crash(*args, **kwargs):
        seen.append("paid-call")
        raise SystemExit("simulated crash after AI started")
    monkeypatch.setattr("app.services.ai_provider.chat", crash)
    with pytest.raises(SystemExit): comments.suggest_task(db, task)
    assert comment.ai_status == "generating"
    assert comments.suggest_task(db, task)["skipped"] == "ai_receipt_uncertain"
    assert len(seen) == 1 and comment.ai_status == "uncertain"
    assert admin.post(f"/api/comments/{comment.id}/suggest").status_code == 409
    task.status = "failed"; db.commit()
    assert admin.post(f"/api/tasks/{task.id}/retry").status_code == 409


@respx.mock
def test_pending_poll_with_missing_or_wrong_receipt_never_resends(admin, db):
    values, post = published(db, admin)
    post.status = "processing"
    entry = UsageLedger(tenant_id=post.tenant_id, post_id=post.id, action="publish.post", source="publish_post", status="pending", cost_micros=None)
    db.add(entry); db.commit()
    route = respx.get(BASE + "/uploadposts/status").mock(return_value=httpx.Response(200, json={"request_id": "different", "status": "completed", "results": [{"platform": "instagram", "success": True, "post_id": "wrong"}]}))
    posts.reconcile(db, post, poll=180)
    assert post.status == "uncertain" and entry.status == "uncertain" and route.call_count == 1
    assert all(c.request.method == "GET" for c in respx.calls)


@respx.mock
def test_reply_crash_keeps_confirmation_and_refuses_second_send(admin, db, monkeypatch):
    values, post = published(db, admin)
    comment = Comment(tenant_id=post.tenant_id, post_id=post.id, remote_id="c1", text="Price?")
    db.add(comment); db.commit()
    respx.get(BASE + "/uploadposts/users").mock(return_value=httpx.Response(200, json=remote()))
    route = respx.post(BASE + "/uploadposts/comments/create").mock(return_value=httpx.Response(200, json={"success": True, "id": "reply-123"}))
    real = UploadPost.request
    def crash(provider, method, path, **kwargs):
        response = real(provider, method, path, **kwargs)
        if method == "POST": raise SystemExit("simulated reply receipt loss")
        return response
    monkeypatch.setattr(UploadPost, "request", crash)
    with pytest.raises(SystemExit): comments.reply(db, values[0], comment, "Thanks", comments.version(comment))
    assert comment.reply_status == "sending" and comment.reply_text == "Thanks"
    r = admin.post(f"/api/comments/{comment.id}/reply", json={"text": "Thanks", "version": comments.version(comment), "confirmed": True})
    assert r.status_code == 409 and route.call_count == 1


def test_foreign_posts_and_comments_cannot_be_read_reconciled_or_replied(admin, db):
    values, post = published(db, admin)
    comment = Comment(tenant_id=post.tenant_id, post_id=post.id, remote_id="c1", text="Private")
    db.add(comment); db.commit()
    other = Tenant(id=new_id(), name="Other factory"); db.add(other); db.flush()
    post.tenant_id, comment.tenant_id = other.id, other.id
    db.commit()
    assert admin.get("/api/posts").json()["data"]["total"] == 0
    assert admin.get("/api/comments").json()["data"]["total"] == 0
    assert admin.post(f"/api/posts/{post.id}/reconcile").status_code == 404
    assert admin.post(f"/api/posts/{post.id}/sync-comments").status_code == 404
    assert admin.post(f"/api/comments/{comment.id}/suggest").status_code == 404
    assert admin.post(f"/api/comments/{comment.id}/reply", json={"text": "Reply", "version": comments.version(comment), "confirmed": True}).status_code == 404


@respx.mock
def test_ai_timeout_preserves_unknown_cost_and_refuses_automatic_repeat(admin, db):
    values, post = published(db, admin)
    assert admin.post("/api/channels", json={"provider": "deepseek", "api_key": "sk-test-1234567890abcd"}).status_code == 200
    comment = Comment(tenant_id=post.tenant_id, post_id=post.id, remote_id="c1", text="Price?")
    db.add(comment); db.commit()
    route = respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=httpx.ReadTimeout("sensitive-test-placeholder"))
    r = admin.post(f"/api/comments/{comment.id}/suggest")
    assert r.status_code == 502
    db.refresh(comment)
    assert comment.ai_status == "uncertain"
    entry = db.scalars(select(UsageLedger).where(UsageLedger.source == "comment_suggest")).one()
    assert entry.status == "uncertain" and entry.cost_micros is None
    assert admin.post(f"/api/comments/{comment.id}/suggest").status_code == 409 and route.call_count == 1
