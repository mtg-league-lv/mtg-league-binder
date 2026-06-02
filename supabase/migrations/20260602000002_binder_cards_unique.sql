alter table binder_cards
  add constraint binder_cards_binder_id_card_name_unique unique (binder_id, card_name);
