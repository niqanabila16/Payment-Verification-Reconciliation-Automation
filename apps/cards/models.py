"""
Card activation (revision 2, point 16) and card stock monitoring (revision 3).

* Physical cards: Customer service (CS) uploads a batch file sent by head office; only the "Card No" column is stored, in the
  exact order of the file. CS delivers selected cards to a branch ("Delivered"); the branch Teller confirms receipt ("Accepted").
* Card requests: a Teller picks one card of the own branch for a customer, fills in the customer data and sends the customer's
  PDF to CS. The card is then "Collected" by the customer. CS asks head office by e-mail (outside the system), then records
  "Activation Requested", "Card Activated" or "Reject" (a reason from a list + a follow-up type).
* Blocked cards: CS (with the right to do so) blocks a card of a branch and writes the reason.

Storage notes (revision 3): every status / reason / type is a SMALLINT code (2 bytes) instead of a text value; the card number is
a VARCHAR(19) (the longest card number there is); dates that exist only for some cards are NULL-able columns; the rare "blocked"
data lives in its own small table so the big card table carries no empty columns for it.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.models import Branch


class CardUpload(models.Model):
    """One file with card numbers uploaded by CS."""

    file_name = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64, db_index=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="card_uploads")
    uploaded_at = models.DateTimeField(default=timezone.now)
    card_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self) -> str:
        return f"{self.file_name} ({self.card_count})"


class CardStatus(models.IntegerChoices):
    NOT_SENT = 0, "Not Sent"          # still at head office  -> "Total Undisbursed Card"
    DELIVERED = 1, "Delivered"        # sent to a branch, not confirmed by the Teller yet
    ACCEPTED = 2, "Accepted"          # confirmed by the Teller
    COLLECTED = 3, "Collected"        # given to a customer (a card request exists)
    BLOCKED = 4, "Blocked"            # blocked by CS, with a reason

    @property
    def slug(self) -> str:
        return self.name.lower()


# The slug (name in lower case) is what the tabs and the URLs show: ?tab=not_sent, ?tab=blocked ...
CARD_STATUS_BY_SLUG = {s.name.lower(): s for s in CardStatus}
AT_BRANCH_FREE = (CardStatus.DELIVERED, CardStatus.ACCEPTED)       # a card the branch still has: counted as "Remaining"
DISBURSED = (CardStatus.DELIVERED, CardStatus.ACCEPTED, CardStatus.COLLECTED, CardStatus.BLOCKED)  # every card that left head office

CARD_NO_MAX = 19                       # ISO/IEC 7812: a card number has at most 19 digits


class Card(models.Model):
    upload = models.ForeignKey(CardUpload, on_delete=models.CASCADE, related_name="cards")
    position = models.PositiveIntegerField(help_text="Row order inside the uploaded file (0 = first card). Lists are always shown in this order.")
    card_no = models.CharField(max_length=CARD_NO_MAX, unique=True)
    status = models.PositiveSmallIntegerField(choices=CardStatus.choices, default=CardStatus.NOT_SENT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="cards")
    created_at = models.DateTimeField(default=timezone.now, help_text="Upload (extraction) time: the date shown while the card is Not Sent.")
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    collected_at = models.DateTimeField(null=True, blank=True, help_text="Customer Collection Date: when a Teller gave the card to a customer.")

    class Meta:
        ordering = ["upload_id", "position", "id"]
        indexes = [
            # one index for the tab lists (status) and the dashboard / branch lists (status, branch); the FK adds the branch-only index
            models.Index(fields=["status", "branch"], name="card_status_branch_idx"),
        ]

    def __str__(self) -> str:
        return self.card_no

    @property
    def shown_at(self):
        """Date and time column: the upload time, replaced by the delivery time once the card is Delivered."""
        return self.delivered_at or self.created_at

    @property
    def tone(self) -> str:
        return {CardStatus.ACCEPTED: "success", CardStatus.COLLECTED: "success", CardStatus.DELIVERED: "info",
                CardStatus.BLOCKED: "danger"}.get(self.status, "neutral")


class CardBlock(models.Model):
    """Why and by whom a card was blocked. One row per blocked card (the card number is the key, so no extra id / index)."""

    card = models.OneToOneField(Card, primary_key=True, on_delete=models.CASCADE, related_name="block")
    note = models.CharField(max_length=255)
    blocked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    blocked_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.card_id}: {self.note}"


class RequestStatus(models.IntegerChoices):
    SENT = 0, "Sent"
    ACTIVATION_REQUESTED = 1, "Activation Requested"
    ACTIVATED = 2, "Card Activated"
    REJECTED = 3, "Reject"

    @property
    def tone(self) -> str:
        return {2: "success", 3: "danger", 1: "info"}.get(self.value, "neutral")


class FollowUp(models.IntegerChoices):
    """The type CS picks for a Reject (Excel column "Follow Up")."""

    INCOMPLETE = 1, "Incomplete Data"
    RETURN = 2, "Return"
    CLOSE = 3, "Close"


class RejectReason(models.IntegerChoices):
    """The reason CS picks for a Reject (Excel column "Note")."""

    MOTHER_NAME = 1, "Nama Ibu Kandung"
    SIGNATURE = 2, "Tanda Tangan Berbeda"
    BIRTH = 3, "TTL Berbeda"
    KTP = 4, "KTP Tidak Sesuai DUKCAPIL"


class CardReason(models.IntegerChoices):
    """Why the customer needs a card (Excel column "Alasan Ganti Kad")."""

    NEW = 1, "Terbit Kartu Baru"
    REPLACE = 2, "Ganti Kartu"
    EXPIRED = 3, "Kad Expired"


# After a Reject the Teller may send a corrected PDF again, except when CS closed the request.
RESUBMITTABLE = (FollowUp.INCOMPLETE, FollowUp.RETURN)


def activation_upload_path(instance, filename) -> str:
    """Random name on disk (the customer's file name is kept in `file_name`), so names can never clash or escape the folder."""
    return f"activation/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.pdf"


class ActivationRequest(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="activation_requests")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="activation_requests")
    card = models.OneToOneField(Card, null=True, blank=True, on_delete=models.PROTECT, related_name="request",
                                help_text="The card given to the customer. Empty only for requests made before revision 3.")
    customer_name = models.CharField(max_length=100, blank=True)          # Nama Pemohon
    account_no = models.CharField(max_length=20, blank=True)              # No Rekening (text: keeps leading zeros)
    id_no = models.CharField(max_length=20, blank=True)                   # No ID (KTP / passport)
    phone = models.CharField(max_length=20, blank=True)                   # No Phone Nasabah
    reason = models.PositiveSmallIntegerField(choices=CardReason.choices, null=True, blank=True)
    file = models.FileField(upload_to=activation_upload_path)
    file_name = models.CharField(max_length=255, help_text="Original file name of the customer's PDF.")
    submitted_at = models.DateTimeField(default=timezone.now)             # "Date Submit to HQ"
    status = models.PositiveSmallIntegerField(choices=RequestStatus.choices, default=RequestStatus.SENT, db_index=True)
    follow_up = models.PositiveSmallIntegerField(choices=FollowUp.choices, null=True, blank=True)
    reject_reason = models.PositiveSmallIntegerField(choices=RejectReason.choices, null=True, blank=True)
    cs_note = models.TextField(blank=True, help_text="Legacy free-text note of requests rejected before revision 3. Not used any more.")
    status_changed_at = models.DateTimeField(default=timezone.now)
    mabes_at = models.DateTimeField(null=True, blank=True, help_text="When CS recorded Activation Requested (Date Submit to Mabes).")
    activated_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resubmit_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        indexes = [models.Index(fields=["branch", "-submitted_at"], name="actreq_branch_idx")]

    def __str__(self) -> str:
        return f"{self.customer_name or self.file_name} ({self.get_status_display()})"

    @property
    def tone(self) -> str:
        return RequestStatus(self.status).tone

    @property
    def note_text(self) -> str:
        """What the Teller and CS read in the Note column: the chosen reason (or the legacy note of an old request)."""
        if self.reject_reason:
            return self.get_reject_reason_display()
        return self.cs_note
