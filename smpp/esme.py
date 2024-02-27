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
    
    def _sent_handler(self, pdu, msisdn):
        logger.info('submit_sm_resp seqno: {} msgid: {}'
                     .format(pdu.sequence, pdu.message_id))
        try:
            redis.set(f"{self.settings.redis_sent_key}/{msisdn}", "True")
        except Exception as e:
            logger.error(f'Error while setting is_sent/{msisdn} in Redis: {e}')

    def _received_handler(self, pdu, msisdn):
        logger.info('delivered msgid:{}'.format(pdu.receipted_message_id))
        self.is_sending = False

        try:
            redis.set(f"{self.settings.redis_delivered_key}/{msisdn}", "True")
        except Exception as e:
            logger.error(f'Error while setting is_delivered/{msisdn} in Redis: {e}')

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

        if self.client.state == smpplib.client.consts.SMPP_CLIENT_STATE_CLOSED:
            logger.info('Connecting to SMPP server.')
            self.client.connect()

        if self.client.state == smpplib.client.consts.SMPP_CLIENT_STATE_OPEN:
            logger.info('Binding to SMPP server.')
            self.client.bind_transceiver(
                system_id=self.settings.smsc_system_id,
                password=self.settings.smsc_password,
            )

    def disconnect(self) -> None:
        if self.client.state in {
            smpplib.client.consts.SMPP_CLIENT_STATE_BOUND_RX,
            smpplib.client.consts.SMPP_CLIENT_STATE_BOUND_TX,
            smpplib.client.consts.SMPP_CLIENT_STATE_BOUND_TRX,
        }:
            self.client.unbind()
        if self.client.state == smpplib.client.consts.SMPP_CLIENT_STATE_OPEN:
            self.client.disconnect()

    async def send_message(self, msisdn, message):
        if self.client is None \
        or self.client.state != smpplib.client.consts.SMPP_CLIENT_STATE_BOUND_TRX:
            logger.info('Client is not connected or not bound. Reconnecting...')
            self.connect()

        self.is_sending = True
        self.client.set_message_sent_handler(
            lambda pdu: self._sent_handler(pdu, msisdn)
        )
        self.client.set_message_received_handler(
            lambda pdu: self._received_handler(pdu, msisdn)
        )

        parts, encoding_flag, msg_type_flag = smpplib.gsm.make_parts(message)
        try:
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
        except Exception as e:
            logger.error('Error while sending message to {}: {}'.format(msisdn, e))
            self.is_sending = False
            return False
        
        while self.is_sending:
            try:
                self.client.read_once(
                    ignore_error_codes=None,
                    auto_send_enquire_link=True,
                )
            except Exception as e:
                logger.error('Error while sending message to {}: {}'.format(msisdn, e))
                self.is_sending = False
                return False
        
        logger.info('Message successfully sent to {}'.format(msisdn))
        return True


if __name__ == '__main__':
    ''' This is an example code for ESME. It sends two messages to two different
    MSISDNs.
    '''
    from settings import settings
    esme = ESME(settings())
    esme.connect()
    
    esme.send_message(
        msisdn='06304988888',
        message='Hello World!',
    )
    esme.send_message(
        msisdn='06304988842',
        message='Hi person!',
    )

    esme.disconnect()
    