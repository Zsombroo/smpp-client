from threading import Thread

import smpplib

from settings import SmppSettings
from utils.logger import logger
from utils.redis_service import redis


class ESME:
    ''' External Short Message Entity
    '''

    def __init__(self, settings: SmppSettings) -> None:
        self.settings: SmppSettings = settings
        self.client: smpplib.client.Client = None
        self.is_sending: bool = False
        self.thread: Thread = None
    
    def _sent_handler(self, pdu, msisdn):
        logger.info('submit_sm_resp seqno: {} msgid: {} msisdn: {}'
                     .format(pdu.sequence, pdu.message_id, msisdn))
        try:
            redis.set(f"{self.settings.redis_sent_key}/{msisdn}", "True")
        except Exception as e:
            logger.error(f'Error while setting {self.settings.redis_sent_key}/{msisdn} in Redis: {e}')

    def _received_handler(self, pdu, msisdn):
        logger.info('delivered msgid:{} msisdn: {}'
                    .format(pdu.receipted_message_id, msisdn))
        self.is_sending = False
        try:
            redis.set(f"{self.settings.redis_delivered_key}/{msisdn}", "True")
        except Exception as e:
            logger.error(f'Error while setting {self.settings.redis_delivered_key}/{msisdn} in Redis: {e}')

        return 0

    def connect(self) -> None:
        if self.client is None:
            logger.info('Creating new SMPP client.')
            self.client = smpplib.client.Client(
                host=self.settings.smsc_host,
                port=self.settings.smsc_port,
                allow_unknown_opt_params=True,
                timeout=60,
            )
        else:
            logger.info('Client already exists. Skipping creation.')
        if self.client.state == smpplib.client.consts.SMPP_CLIENT_STATE_CLOSED:
            logger.info('Connecting to SMPP server.')
            self.client.connect()
        else:
            logger.info('Client is already connected. Skipping connect. Client state: {}'
                        .format(self.client.state))
        if self.client.state == smpplib.client.consts.SMPP_CLIENT_STATE_OPEN:
            logger.info('Binding to SMPP server.')
            self.client.bind_transceiver(
                system_id=self.settings.smsc_system_id,
                password=self.settings.smsc_password,
            )
        else:
            logger.info('Client in wrong state. Skipping bind. Client state: {}'
                        .format(self.client.state))
        logger.info('Starting listener thread.')
        self.thread = Thread(target=self.client.listen)
        self.thread.start()

    def disconnect(self) -> None:
        if self.client.state in {
            smpplib.client.consts.SMPP_CLIENT_STATE_BOUND_RX,
            smpplib.client.consts.SMPP_CLIENT_STATE_BOUND_TX,
            smpplib.client.consts.SMPP_CLIENT_STATE_BOUND_TRX,
        }:
            logger.info('Unbinding from SMPP server.')
            self.client.unbind()
        else:
            logger.info('Client is not bound. Skipping unbind. Client state: {}'
                        .format(self.client.state))
        if self.client.state == smpplib.client.consts.SMPP_CLIENT_STATE_OPEN:
            logger.info('Disconnecting from SMPP server.')
            self.client.disconnect()
        else:
            logger.info('Client is not connected. Skipping disconnect. Client state: {}'
                        .format(self.client.state))

    def send_message(self, msisdn, message):
        if self.client is None \
        or self.client.state == smpplib.client.consts.SMPP_CLIENT_STATE_CLOSED:
            logger.info('Client is not connected or not bound. Reconnecting...')
            self.connect()
        if self.thread is None or not self.thread.is_alive():
            logger.info('Thread is not running. Starting listener thread.')
            self.thread = Thread(target=self.client.listen)
            self.thread.start()

        self.is_sending = True
        self.client.set_message_sent_handler(
            lambda pdu: self._sent_handler(pdu, msisdn)
        )
        self.client.set_message_received_handler(
            lambda pdu: self._received_handler(pdu, msisdn)
        )

        out = {
            'status': 'success',
            'code': 200,
            'message': 'Message successfully sent to {}'.format(msisdn)
        }

        parts, encoding_flag, msg_type_flag = smpplib.gsm.make_parts(message)
        try:
            logger.info(
                {
                    "SMPP INFO": {
                        "function": "send_message",
                        "msisdn": msisdn,
                        "log": "Attempting to send message",
                        "state": self.client.state,
                        "source_addr_ton": smpplib.consts.SMPP_TON_ALNUM,
                        "source_addr_npi": smpplib.consts.SMPP_NPI_ISDN,
                        "source_addr": self.settings.source_addr,
                        "dest_addr_ton": smpplib.consts.SMPP_TON_INTL,
                        "dest_addr_npi": smpplib.consts.SMPP_NPI_ISDN,
                        "destination_addr": msisdn,
                        "short_message": parts,
                        "data_coding": encoding_flag,
                        "esm_class": msg_type_flag,
                    }
                },
            )
            for part in parts:
                pdu = self.client.send_message(
                    source_addr_ton=smpplib.consts.SMPP_TON_ALNUM,
                    source_addr_npi=smpplib.consts.SMPP_NPI_ISDN,
                    # Make sure it is a byte string, not unicode:
                    source_addr=self.settings.source_addr,

                    dest_addr_ton=smpplib.consts.SMPP_TON_INTL,
                    dest_addr_npi=smpplib.consts.SMPP_NPI_ISDN,
                    # Make sure these two params are byte strings, not unicode:
                    destination_addr=msisdn,
                    short_message=part,

                    data_coding=encoding_flag,
                    esm_class=msg_type_flag,
                    registered_delivery=True,
                )
                logger.info('submit_sm {}->{} seqno: {}'.format(
                    pdu.source_addr,
                    pdu.destination_addr,
                    pdu.sequence
                ))
        except smpplib.exceptions.ConnectionError as e:
            logger.error('ConnectionError while sending message to {}: {}'.format(msisdn, e))
            out = {
                'status': 'failed',
                'code': 520,
                'message': 'ConnectionError while sending message to {}'.format(msisdn)
            }
        except smpplib.exceptions.PDUError as e:
            logger.error('PDUError while sending message to {}: {}'.format(msisdn, e))
            out = {
                'status': 'failed',
                'code': 521,
                'message': 'PDUError while sending message to {}'.format(msisdn)
            }
        except smpplib.exceptions.UnknownCommandError as e:
            logger.error('UnknownCommandError while sending message to {}: {}'.format(msisdn, e))
            out = {
                'status': 'failed',
                'code': 522,
                'message': 'UnknownCommandError while sending message to {}'.format(msisdn)
            }
        except Exception as e:
            logger.error('Error while sending message to {}: {}'.format(msisdn, e))
            out = {
                'status': 'failed',
                'code': 523,
                'message': 'Generic Exception while sending message to {}'.format(msisdn)
            }

        logger.info('Message successfully sent to {}'.format(msisdn))
        return out


if __name__ == '__main__':
    ''' This is an example code for ESME. It sends two messages to two different
    MSISDNs.
    '''
    from settings import settings
    esme = ESME(settings)
    esme.connect()
    
    esme.send_message(
        msisdn='06304988888',
        message='Hello',
    )

    esme.disconnect()
    