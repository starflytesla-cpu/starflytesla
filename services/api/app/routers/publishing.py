from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.deps import DB, AdminUser
from app.models import Comment, Post, PublishChannel, SocialAccount, Video, new_id
from app.schemas import AccountUpdateIn, BindAccountsIn, PostCopyIn, ReplyCommentIn, SchedulePostIn, ok
from app.services import comments, posts, social_accounts
from app.services.upload_post import UploadPost

router = APIRouter(prefix="/api", tags=["publishing"])


@router.get("/social-accounts")
def accounts(admin: AdminUser, db: DB):
    rows = db.scalars(select(SocialAccount).where(SocialAccount.tenant_id == admin.tenant_id).order_by(SocialAccount.created_at)).all()
    return ok([social_accounts.out(row) for row in rows])


@router.get("/social-accounts/remote-profiles")
def remote_profiles(admin: AdminUser, db: DB, channel_id: str = Query(max_length=36)):
    channel = social_accounts.owned(db, PublishChannel, admin.tenant_id, channel_id)
    return ok(UploadPost(channel).profiles())


@router.post("/social-accounts/bind")
def bind(body: BindAccountsIn, admin: AdminUser, db: DB):
    rows = social_accounts.bind(db, admin, body.channel_id, body.profile_id, body.remote_profile, body.platforms)
    return ok([social_accounts.out(row) for row in rows], "帳號已綁定")


@router.patch("/social-accounts/{account_id}")
def update(account_id: str, body: AccountUpdateIn, admin: AdminUser, db: DB):
    account = social_accounts.owned(db, SocialAccount, admin.tenant_id, account_id, lock=True)
    if body.enabled is not None:
        account.enabled = body.enabled
    if body.auto_suggest_enabled is not None:
        account.auto_suggest_enabled = body.auto_suggest_enabled
        account.auto_suggest_by = admin.id if body.auto_suggest_enabled else None
    db.commit()
    return ok(social_accounts.out(account), "已儲存")


@router.post("/social-accounts/{account_id}/check")
def check(account_id: str, admin: AdminUser, db: DB):
    account = social_accounts.owned(db, SocialAccount, admin.tenant_id, account_id, lock=True)
    social_accounts.check(db, account)
    db.commit()
    return ok(social_accounts.out(account), "已重新檢查授權")


@router.get("/posts")
def list_posts(admin: AdminUser, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    where = Post.tenant_id == admin.tenant_id
    total = db.scalar(select(func.count()).select_from(Post).where(where))
    rows = db.scalars(select(Post).where(where).order_by(Post.schedule_at.desc()).limit(limit).offset(offset)).all()
    return ok({"items": [posts.out(row) for row in rows], "total": total})


@router.post("/posts/copy")
def generate_copy(body: PostCopyIn, admin: AdminUser, db: DB):
    video = social_accounts.owned(db, Video, admin.tenant_id, body.video_id)
    return ok(posts.copy(db, admin, video, body.platform), "AI 貼文草稿已產生，請閱讀並確認")


@router.get("/posts/request-key")
def request_key(admin: AdminUser):
    return ok({"request_key": new_id()})


@router.post("/posts")
def schedule(body: SchedulePostIn, admin: AdminUser, db: DB):
    return ok(posts.out(posts.schedule(db, admin, body)), "已保存人工確認並排入發佈")


@router.post("/posts/{post_id}/cancel")
def cancel(post_id: str, admin: AdminUser, db: DB):
    post = social_accounts.owned(db, Post, admin.tenant_id, post_id, lock=True)
    posts.cancel(db, post)
    return ok(posts.out(post), "排程已取消")


@router.post("/posts/{post_id}/reconcile")
def reconcile(post_id: str, admin: AdminUser, db: DB):
    post = social_accounts.owned(db, Post, admin.tenant_id, post_id, lock=True)
    posts.reconcile(db, post)
    return ok(posts.out(post), "已查詢原請求回執；未重新發佈")


@router.post("/posts/{post_id}/sync-comments")
def sync_comments(post_id: str, admin: AdminUser, db: DB):
    post = social_accounts.owned(db, Post, admin.tenant_id, post_id, lock=True)
    return ok({"comments": comments.sync(db, post)}, "評論已同步")


@router.get("/comments")
def list_comments(admin: AdminUser, db: DB, unreplied: bool = False, negative: bool = False,
                  post_id: str | None = Query(None, max_length=36), limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    where = [Comment.tenant_id == admin.tenant_id]
    if unreplied:
        where.append(Comment.reply_status.in_(("unreplied", "failed")))
    if negative:
        where.append(Comment.intent == "complaint")
    if post_id:
        where.append(Comment.post_id == post_id)
    total = db.scalar(select(func.count()).select_from(Comment).where(*where))
    rows = db.scalars(select(Comment).where(*where).order_by(Comment.created_at.desc()).limit(limit).offset(offset)).all()
    return ok({"items": [comments.out(row) for row in rows], "total": total})


@router.post("/comments/{comment_id}/suggest")
def suggest(comment_id: str, admin: AdminUser, db: DB):
    comment = social_accounts.owned(db, Comment, admin.tenant_id, comment_id, lock=True)
    comments.suggest(db, admin, comment)
    db.refresh(comment)
    return ok(comments.out(comment), "AI 建議已保存，尚未送出")


@router.post("/comments/{comment_id}/reply")
def reply(comment_id: str, body: ReplyCommentIn, admin: AdminUser, db: DB):
    comment = social_accounts.owned(db, Comment, admin.tenant_id, comment_id, lock=True)
    comments.reply(db, admin, comment, body.text, body.version)
    return ok(comments.out(comment), "回覆已送出並取得平台回執")
