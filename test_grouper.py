"""Slice 2 tests — send immediately, SL edits, silent target exits, SL-hit kept."""
from grouper import PositionTracker


def entry(symbol="NIFTY 24500 CE", side="B", price=142.5, order="E1"):
    return {"Symbol": symbol, "TxnType": side, "TradedPrice": price, "Status": "TRADED",
            "OrderNo": order, "Quantity": 50, "Product": "I", "OrderDateTime": "2024-09-11 10:16:02"}


def test_entry_sends_immediately_with_placeholders():
    tr = PositionTracker()
    action, pos = tr.handle(entry())
    assert action == "send"
    assert pos.entry_price == 142.5 and pos.sl is None


def test_sl_arrival_edits_same_position():
    tr = PositionTracker()
    tr.handle(entry())
    action, pos = tr.handle({"Symbol": "NIFTY 24500 CE", "TxnType": "S", "TriggerPrice": 118,
                             "OrderType": "STOP_LOSS_MARKET", "Status": "PENDING",
                             "OrderNo": "SL1", "Quantity": 50})
    assert action == "edit" and pos.sl == 118


def test_target_pending_sends_nothing():
    # no visible change until a fill — avoids edit spam
    tr = PositionTracker()
    tr.handle(entry())
    assert tr.handle({"Symbol": "NIFTY 24500 CE", "TxnType": "S", "Price": 165,
                      "OrderType": "LIMIT", "Status": "PENDING", "OrderNo": "T1"}) is None


def test_super_order_sl_links_via_algo():
    tr = PositionTracker()
    a, p = tr.handle({"Symbol": "NIFTY", "TxnType": "B", "Price": 100, "Status": "TRADED",
                      "OrderNo": "E", "AlgoOrdNo": "A99", "Quantity": 10,
                      "targetPrice": 110, "stopLossPrice": 95})
    assert a == "send" and p.sl == 95


def test_remarks_sl_fallback():
    tr = PositionTracker()
    a, p = tr.handle({"tradingSymbol": "BANKNIFTY", "transactionType": "BUY", "price": 500,
                      "orderStatus": "TRADED", "orderId": "E9", "Remarks": "SL:480"})
    assert a == "send" and p.sl == 480


def test_sl_hit_closes_with_label():
    tr = PositionTracker()
    tr.handle(entry())
    tr.handle({"Symbol": "NIFTY 24500 CE", "TxnType": "S", "TriggerPrice": 118,
               "OrderType": "STOP_LOSS_MARKET", "Status": "PENDING", "OrderNo": "SL1"})
    a, p = tr.handle({"Symbol": "NIFTY 24500 CE", "TxnType": "S", "TradedPrice": 118,
                      "OrderType": "STOP_LOSS_MARKET", "Status": "TRADED", "OrderNo": "SL1"})
    assert a == "edit" and "SL hit" in p.exit_info and "🔻" in p.exit_info


def test_lone_cancelled_sends_nothing():
    tr = PositionTracker()
    assert tr.handle({"Symbol": "NIFTY", "TxnType": "B", "Price": 100,
                      "Status": "CANCELLED", "OrderNo": "CX"}) is None


def test_partial_exit_keeps_slot_open_silently():
    tr = PositionTracker()
    tr.handle(entry())  # qty 50
    a, p = tr.handle({"Symbol": "NIFTY 24500 CE", "TxnType": "S", "TradedPrice": 150,
                      "OrderType": "LIMIT", "Status": "TRADED", "OrderNo": "T1",
                      "Quantity": 25})
    assert a == "edit" and "Booked" in p.exit_info  # partial exit now labelled
    assert p.entry_price == 142.5  # entry average untouched


def test_full_exit_closes_slot_next_entry_sends_fresh():
    tr = PositionTracker()
    tr.handle(entry())
    tr.handle({"Symbol": "NIFTY 24500 CE", "TxnType": "S", "TradedPrice": 150,
               "OrderType": "MARKET", "Status": "TRADED", "OrderNo": "SQ1",
               "Quantity": 50})
    a, _ = tr.handle(entry(order="E2"))
    assert a == "send"
