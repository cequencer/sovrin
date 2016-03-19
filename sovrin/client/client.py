import json
from base64 import b64decode
from typing import Mapping, List, Any, Dict, Union, Tuple

import pickle

import base58
from plenum.client.client import Client as PlenumClient
from plenum.client.signer import Signer
from plenum.common.request_types import OP_FIELD_NAME, Request
from plenum.common.stacked import HA
from plenum.common.txn import REQACK, REPLY, REQNACK
from plenum.common.util import getlogger, getMaxFailures, \
    getSymmetricallyEncryptedVal, libnacl

from sovrin.client.client_storage import ClientStorage
from sovrin.common.txn import TXN_TYPE, ADD_ATTR, DATA, TXN_ID, TARGET_NYM, SKEY, \
    DISCLOSE, NONCE, ORIGIN, GET_ATTR

logger = getlogger()


class Client(PlenumClient):
    def __init__(self,
                 name: str,
                 nodeReg: Dict[str, HA]=None,
                 ha: Union[HA, Tuple[str, int]]=None,
                 lastReqId: int = 0,
                 signer: Signer=None,
                 signers: Dict[str, Signer]=None,
                 basedirpath: str=None):
        super().__init__(name,
                         nodeReg,
                         ha,
                         lastReqId,
                         signer,
                         signers,
                         basedirpath)
        self.storage = self.getStorage()
        self.lastReqId = self.storage.getLastReqId()
        # Attributes stored as tuple of 3 elements origin, secretKey, txnId
        self.attributes = {}    # type: Dict[int, List[Tuple[str, str, str]]]

    def setupDefaultSigner(self):
        # Sovrin clients should use a wallet, which supplies the signers
        pass

    def getStorage(self):
        return ClientStorage(self.name)

    def submit(self, *operations: Mapping, identifier: str=None) -> List[Request]:
        keys = []
        for op in operations:
            if op[TXN_TYPE] == ADD_ATTR:
                data = op[DATA]
                encVal, secretKey = getSymmetricallyEncryptedVal(data)
                op[DATA] = encVal
                keys.append(secretKey)
        requests = super().submit(*operations, identifier=identifier)
        for r in requests:
            self.storage.addRequest(r)
            operation = r.operation
            if operation[TXN_TYPE] == ADD_ATTR:
                self.attributes[r.reqId] = (r.identifier, keys.pop(), None)
        return requests

    def handleOneNodeMsg(self, wrappedMsg) -> None:
        super().handleOneNodeMsg(wrappedMsg)
        msg, sender = wrappedMsg
        if OP_FIELD_NAME not in msg:
            logger.error("Op absent in message {}".format(msg))
        if msg[OP_FIELD_NAME] == REQACK:
            self.storage.addAck(msg, sender)
        elif msg[OP_FIELD_NAME] == REQNACK:
            self.storage.addNack(msg, sender)
        elif msg[OP_FIELD_NAME] == REPLY:
            result = msg['result']
            # TODO: This is just for now. As soon as the client finds out
            # that the attribute is added it discloses it
            reqId = msg["reqId"]
            if reqId in self.attributes and not self.attributes[reqId][2]:
                origin = self.attributes[reqId][0]
                key = self.attributes[reqId][1]
                txnId = result[TXN_ID]
                self.attributes[reqId] = (origin, key, txnId)
                self.doAttrDisclose(origin, result[TARGET_NYM], txnId, key)
            self.storage.addReply(msg['reqId'], sender, {'result': result})
        else:
            logger.debug("Invalid op message {}".format(msg))

    def getTxnsByNym(self, nym: str):
        # TODO Implement this
        pass

    def getTxnsByAttribute(self, attrName: str, attrValue: Any=None):
        def cond(result):
            return attrName in result and (attrValue is None or attrValue ==
                                           result[attrName])

        return self.getTxnsByCondition(condition=cond)

    def getTxnsByCondition(self, condition):
        # TODO: This is very inefficient. For a starting point store have a
        # keyspace partition for storing a map of cryptonyms(or txn types or
        # which attribute of interest) to reqIds

        results = {}        # tpye: Dict[int, Tuple[Set[str], Any])
        for k, v in self.storage.replyStore.iterator():
            result = pickle.loads(v)['result']
            if condition(result):
                reqId, sender = k.split(b'-')
                reqId = int(reqId)
                sender = sender.decode()
                if reqId not in results:
                    results[reqId] = (set(), result)
                results[reqId][0].add(sender)
                # TODO: What about different nodes sending differnet replies?
                #  Need to pick reply which is given by f+1 nodes. Having
                # hashes to check for equality might be efficient

        f = getMaxFailures(len(self.nodeReg))
        return [val[1] for rid, val in results.items() if len(val[0]) > f]

    def hasMadeRequest(self, reqId: int):
        return self.storage.hasRequest(reqId)

    def replyIfConsensus(self, reqId: int):
        f = getMaxFailures(len(self.nodeReg))
        replies, errors = self.storage.getAllReplies(reqId)
        r = list(replies.values())[0] if len(replies) > f else None
        e = list(errors.values())[0] if len(errors) > f else None
        return r, e

    # TODO: Just for now. Remove it later
    def doAttrDisclose(self, origin, target, txnId, key):
        box = libnacl.public.Box(b64decode(origin), b64decode(target))

        data = json.dumps({TXN_ID: txnId, SKEY: key})
        nonce, boxedMsg = box.encrypt(data.encode(), pack_nonce=False)

        op = {
            ORIGIN: origin,
            TARGET_NYM: target,
            TXN_TYPE: DISCLOSE,
            NONCE: base58.b58encode(nonce),
            DATA: base58.b58encode(boxedMsg)
        }
        self.submit(op, identifier=origin)

    def doGetAttributeTxn(self, identifier, attrName):
        op = {
            ORIGIN: identifier,
            TARGET_NYM: identifier,
            TXN_TYPE: GET_ATTR,
            # TODO: Need to encrypt get query
            DATA: json.dumps({"name": attrName})
        }
        self.submit(op, identifier=identifier)
