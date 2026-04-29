"""DRF serializers for the service-app REST API."""

from rest_framework import serializers

from apps.service.models import ChatMessage, TutoringSession


class ChatMessageSerializer(serializers.ModelSerializer):
    """Serialize a single chat turn for API responses."""

    class Meta:
        model = ChatMessage
        fields = ('id', 'role', 'content', 'retrieved_chunks', 'model', 'created_at')
        read_only_fields = ('id', 'created_at')


class TutoringSessionSerializer(serializers.ModelSerializer):
    """Serialize a session in list views (no message payload)."""

    subject_name = serializers.CharField(source='subject.name', default=None, read_only=True)
    message_count = serializers.IntegerField(source='messages.count', read_only=True)

    class Meta:
        model = TutoringSession
        fields = (
            'id', 'title', 'subject', 'subject_name', 'is_active',
            'last_message_at', 'created_at', 'message_count',
        )
        read_only_fields = ('id', 'last_message_at', 'created_at', 'subject_name', 'message_count')


class TutoringSessionDetailSerializer(TutoringSessionSerializer):
    """Session payload with embedded messages — used by the detail endpoint."""

    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta(TutoringSessionSerializer.Meta):
        fields = TutoringSessionSerializer.Meta.fields + ('messages',)


class CreateMessageSerializer(serializers.Serializer):
    """Validate the incoming POST body for sending a question."""

    content = serializers.CharField(min_length=1, max_length=4000, trim_whitespace=True)
