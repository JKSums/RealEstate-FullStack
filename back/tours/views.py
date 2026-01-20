from rest_framework import generics, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Tour
from .serializers import TourSerializer, TourCreateSerializer


class IsOwnerOrAgentOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        if hasattr(obj, 'property'):
            return (obj.property.owner == request.user or
                    obj.property.agent == request.user or
                    request.user.is_staff)
        return False


class IsTourCreatorOrPropertyAgent(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS or request.method == 'DELETE':
            return True

        return (obj.agent == request.user or
                (hasattr(obj, 'property') and obj.property.agent == request.user) or
                (hasattr(obj, 'property') and obj.property.owner == request.user))


class TourListCreateView(generics.ListCreateAPIView):
    authentication_classes = [JWTAuthentication]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TourCreateSerializer
        return TourSerializer

    def get_queryset(self):
        if 'property_id' in self.kwargs:
            return Tour.objects.filter(property_id=self.kwargs['property_id'])
        else:
            return Tour.objects.all()

    def get_permissions(self):
        if self.request.method == 'POST':
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        if 'property_id' in self.kwargs:
            from listings.models import Property
            tour_property = Property.objects.get(pk=self.kwargs['property_id'])

            if not tour_property.is_available_for_tour:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("This property is not available for tours.")

            if self.request.user != tour_property.owner and self.request.user != tour_property.agent:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Only property owner or agent can create tours for this property.")

            serializer.save(property=tour_property, agent=self.request.user)
        else:
            tour_property = serializer.validated_data.get('property')

            if tour_property and not tour_property.is_available_for_tour:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("This property is not available for tours.")

            if tour_property and self.request.user != tour_property.owner and self.request.user != tour_property.agent:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Only property owner or agent can create tours for this property.")

            if tour_property and tour_property.agent:
                serializer.save(agent=self.request.user)
            else:
                serializer.save()


class TourDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TourSerializer
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        if 'property_id' in self.kwargs and 'pk' in self.kwargs:
            return Tour.objects.filter(
                property_id=self.kwargs['property_id'],
                id=self.kwargs['pk']
            )
        else:
            return Tour.objects.filter(id=self.kwargs['pk'])

    def get_permissions(self):
        if self.request.method == 'PATCH':
            permission_classes = [IsTourCreatorOrPropertyAgent]
        else:
            permission_classes = [IsOwnerOrAgentOrReadOnly]
        return [permission() for permission in permission_classes]
