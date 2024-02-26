import logging

import smpplib

from settings import SmppSettings


logging.basicConfig(level='INFO')


class ESME:
    def __init__(self, settings: SmppSettings) -> None:
        self.settings: SmppSettings = settings
        self.client: smpplib.client.Client = None
        self.is_sending: bool = False
    
    def _sent_handler(self, pdu):
        logging.info('submit_sm_resp seqno: {} msgid: {}'
                     .format(pdu.sequence, pdu.message_id))

    def _received_handler(self, pdu):
        logging.info('delivered msgid:{}'.format(pdu.receipted_message_id))
        self.is_sending = False
        return 0

    def connect(self) -> None:
        if self.client is None:
            self.client = smpplib.client.Client(
                host=self.settings.smsc_host,
                port=self.settings.smsc_port,
                allow_unknown_opt_params=True,
                timeout=60,
            )
            self.client.set_message_sent_handler(self._sent_handler)
            self.client.set_message_received_handler(self._received_handler)

        if self.client.state == smpplib.client.consts.SMPP_CLIENT_STATE_CLOSED:
            self.client.connect()

        if self.client.state == smpplib.client.consts.SMPP_CLIENT_STATE_OPEN:
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

    def send_message(self, msisdn, message):
        self.connect()

        self.is_sending = True

        parts, encoding_flag, msg_type_flag = smpplib.gsm.make_parts(message)
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
            logging.info('submit_sm {}->{} seqno: {}'.format(
                pdu.source_addr,
                pdu.destination_addr,
                pdu.sequence
            ))
        
        while self.is_sending:
            self.client.read_once(
                ignore_error_codes=None,
                auto_send_enquire_link=True,
            )


if __name__ == '__main__':
    esme = ESME(SmppSettings())
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
    