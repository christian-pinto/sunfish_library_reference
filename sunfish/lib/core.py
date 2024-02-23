# Copyright IBM Corp. 2023
# This software is available to you under a BSD 3-Clause License. 
# The full license terms are available here: https://github.com/OpenFabrics/sunfish_library_reference/blob/main/LICENSE

import os
import uuid

from sunfish.lib.object_handler import ObjectHandler
from sunfish.storage.backend_FS import BackendFS
from sunfish.lib.exceptions import CollectionNotSupported,PropertyNotFound
from sunfish.events.redfish_event_handler import RedfishEventHandler
from sunfish.events.redfish_subscription_handler import RedfishSubscriptionHandler

class Core:

    def __init__(self, conf):
        """init that implements the chosen backend specified in the conf dict.

        Args:
            conf (dict): dictionary where are specified the storage implementation type and the specific backend configuration.
        """

        self.conf = conf
        
        if conf['storage_backend'] == 'FS':
            self.storage_backend = BackendFS(self.conf)
        # elif conf['storage_backend'] == '<OTHER STORAGE>':
            # ...
        
        if conf['handlers']['subscription_handler'] == 'redfish':
            self.subscription_handler = RedfishSubscriptionHandler(self)
        
        if conf['handlers']['event_handler'] == 'redfish':
            self.event_handler = RedfishEventHandler(self)
        
        self.object_handler = ObjectHandler(self)
    
    def get_object(self, path):
        """Calls the correspondent read function from the backend implementation and checks that the path is valid.

        Args:
            path (str): path of the resource. It should comply with Redfish specification.

        Raises:
            InvalidPath: custom exception that is raised if the path is not compliant with the current Redfish specification.

        Returns:
            str|exception: str of the requested resource or an exception in case of fault. 
        """
        # call function from backend
        return self.storage_backend.read(path)
        
    def create_object(self, path, payload:dict):
        """Calls the correspondent create function from the backend implementation. 
        Before to call the create function it generates a unique uuid and updates the payload adding Id and @odata.id.
        To distinguish the storage of an element from the storage of an EventDestination (event subscription schema) the property 'Destination' is checked 
        because it belongs only to EventDestination and it is required.
        @odata.type is checked to verify that this is not a try to store a Collection (forbidden)

        Args:
            payload (resource): resource that we want to store.

        Returns:
            str|exception: return the stored resource or an exception in case of fault.
        """
        
        ## before to add the ID and to call the methods there should be the json validation

        # generate unique uuid if is not present
        if not '@odata.id' in payload and not 'Id' in payload:
            id = str(uuid.uuid4())
            to_add = {
                'Id': id,
                '@odata.id': os.path.join(path,id)
            }
            payload.update(to_add)
        

        type = self.__check_type(payload)

        if "Collection" in type:
            raise CollectionNotSupported()
        elif type == "EventDestination":
            try:
                self.subscription_handler.new_subscription(payload)
            except Exception as e:
                return str(e)
        else:
            try:
                handlerfunc = getattr(ObjectHandler, payload['@odata.type'].split(".")[-1])
                handlerfunc(self, payload)
            except AttributeError:
                pass
        # Call function from backend
        return self.storage_backend.write(payload)

    def replace_object(self, payload):
        """Calls the correspondent replace function from the backend implementation.

        Args:
            payload (resource): resource that we want to replace.

        Returns:
            str|exception: return the replaced resource or an exception in case of fault.
        """
        ## controlla odata.type
        type = self.__check_type(payload)

        if "Collection" in type:
            raise CollectionNotSupported()
        elif type == "EventDestination":
            self.event_handler.delete_subscription(payload)
            self.event_handler.new_subscription(payload)

        # Call function from backend
        return self.storage_backend.replace(payload)
    
    def patch_object(self, path,payload):
        """Calls the correspondent patch function from the backend implementation.

        Args:
            payload (resource): resource that we want to partially update.

        Returns:
            str|exception: return the updated resource or an exception in case of fault.
        """
        obj = self.get_object(path)
        type =obj["@odata.type"]
        if "Collection" in type:
            raise CollectionNotSupported()
        elif type == "EventDestination":
            self.event_handler.delete_subscription(payload)
            resp = self.storage_backend.patch(payload)
            self.event_handler.new_subscription(resp)
            return resp
                    
        # call function from backend
        return self.storage_backend.patch(path,payload)

    def delete_object(self, path):
        """Calls the correspondent remove function from the backend implementation. Checks that the path is valid.

        Args:
            path (str): path of the resource that we want to replace.

        Returns:
            str|exception: return confirmation string or an exception in case of fault.
        """
        ## controlla odata.type
        payload = self.storage_backend.read(path)
        type = self.__check_type(payload)
        if type == "EventDestination":
            self.subscription_handler.delete_subscription(payload)

        # call function from backend
        return self.storage_backend.remove(path)
    
    def handle_event(self, payload):
        if "Context" in payload:
            context = payload["Context"]
        else:
            context = ""
        for event in payload["Events"]:
            try:
                handlerfunc = getattr(RedfishEventHandler, event['MessageId'].split(".")[-1])
                handlerfunc(self, event, context)
            except AttributeError:
                pass
        return self.event_handler.new_event(payload)
            
    def __check_type(self, payload):
        ## controlla odata.type
        if "@odata.type" not in payload:
            raise PropertyNotFound("@odata.type")
        type = payload["@odata.type"]
        type = type.split('.')[0]
        return type.replace("#", "")
