from django.urls import path

from attachments import views

urlpatterns = [
    path("attachments", views.AttachmentListView.as_view()),
    path("attachments/presign", views.PresignView.as_view()),
    path("attachments/<uuid:public_id>/complete", views.CompleteView.as_view()),
]
