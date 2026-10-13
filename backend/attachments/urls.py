from django.urls import path

from attachments import views

urlpatterns = [
    path("attachments", views.AttachmentListView.as_view()),
    path("attachments/presign", views.PresignView.as_view()),
    path("attachments/<uuid:public_id>", views.AttachmentDetailView.as_view()),
    path("attachments/<uuid:public_id>/complete", views.CompleteView.as_view()),
    path("attachments/<uuid:public_id>/download", views.DownloadView.as_view()),
]
