from schema import (
    Bill,
    Customer,
    CustomerPayment,
    Invoice,
    Vendor,
    VendorPayment,
)
from qb_requests import (
    build_bill_add_rq,
    build_bill_payment_check_add_rq,
    build_bill_query_rq,
    build_customer_add_rq,
    build_customer_query_rq,
    build_invoice_add_rq,
    build_invoice_query_rq,
    build_item_query_rq,
    build_receive_payment_add_rq,
    build_vendor_add_rq,
    build_vendor_query_rq,
    parse_bill_add_rs,
    parse_bill_payment_check_add_rs,
    parse_bill_query_rs,
    parse_customer_add_rs,
    parse_customer_query_rs,
    parse_invoice_add_rs,
    parse_invoice_query_rs,
    parse_item_query_rs,
    parse_receive_payment_add_rs,
    parse_vendor_add_rs,
    parse_vendor_query_rs,
)


# -- Customer / Vendor --------------------------------------------------

def test_build_customer_add_rq_home_currency():
    customer = Customer.model_validate({"name": "Acme Corp", "company_name": "Acme Corp Pte Ltd"})
    xml = build_customer_add_rq(customer)
    assert "<Name>Acme Corp</Name>" in xml
    assert "<CompanyName>Acme Corp Pte Ltd</CompanyName>" in xml
    assert "CurrencyRef" not in xml
    assert "<CustomerAddRq><CustomerAdd>" in xml


def test_build_customer_add_rq_multicurrency_and_address():
    customer = Customer.model_validate(
        {"name": "Acme Corp", "currency": "CHF", "address_lines": ["1 Main St", "Suite 2"]}
    )
    xml = build_customer_add_rq(customer)
    assert "<CurrencyRef><FullName>Swiss Franc</FullName></CurrencyRef>" in xml
    assert "<BillAddress><Addr1>1 Main St</Addr1><Addr2>Suite 2</Addr2></BillAddress>" in xml


def test_parse_customer_add_rs_success():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <CustomerAddRs statusCode="0" statusMessage="Status OK">
        <CustomerRet><ListID>800000-1</ListID><Name>Acme Corp</Name></CustomerRet>
      </CustomerAddRs>
    </QBXMLMsgsRs></QBXML>"""
    result = parse_customer_add_rs(response)
    assert result == {"status_code": 0, "status_message": "Status OK", "list_id": "800000-1", "name": "Acme Corp"}


def test_customer_query_round_trip():
    request = build_customer_query_rq(["Acme Corp", "Other Corp"])
    assert "<FullName>Acme Corp</FullName>" in request
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <CustomerQueryRs>
        <CustomerRet><FullName>Acme Corp</FullName></CustomerRet>
      </CustomerQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    assert parse_customer_query_rs(response) == {"Acme Corp"}


def test_build_vendor_add_rq():
    vendor = Vendor.model_validate({"name": "Acme Supplier", "currency": "EUR", "address_lines": ["9 Vendor Rd"]})
    xml = build_vendor_add_rq(vendor)
    assert "<Name>Acme Supplier</Name>" in xml
    assert "<CurrencyRef><FullName>Euro</FullName></CurrencyRef>" in xml
    assert "<VendorAddress><Addr1>9 Vendor Rd</Addr1></VendorAddress>" in xml


def test_parse_vendor_add_rs_error():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <VendorAddRs statusCode="3100" statusMessage="Duplicate name">
      </VendorAddRs>
    </QBXMLMsgsRs></QBXML>"""
    result = parse_vendor_add_rs(response)
    assert result["status_code"] == 3100
    assert result["list_id"] is None


def test_vendor_query_round_trip():
    request = build_vendor_query_rq(["Acme Supplier"])
    assert "<FullName>Acme Supplier</FullName>" in request
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <VendorQueryRs>
        <VendorRet><FullName>Acme Supplier</FullName></VendorRet>
      </VendorQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    assert parse_vendor_query_rs(response) == {"Acme Supplier"}


# -- Items ------------------------------------------------------------------

def test_item_query_round_trip_mixed_item_types():
    request = build_item_query_rq(["Consulting", "Product A"])
    assert "<FullName>Consulting</FullName>" in request
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <ItemQueryRs>
        <ItemServiceRet><FullName>Consulting</FullName></ItemServiceRet>
        <ItemNonInventoryRet><FullName>Product A</FullName></ItemNonInventoryRet>
      </ItemQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    assert parse_item_query_rs(response) == {"Consulting", "Product A"}


# -- Invoices ---------------------------------------------------------------

def test_build_invoice_add_rq_home_currency_with_qty_rate():
    invoice = Invoice.model_validate(
        {
            "ref_number": "INV-1001",
            "customer": "Acme Corp",
            "date": "2026-07-01",
            "memo": "July consulting",
            "lines": [
                {"item": "Consulting", "quantity": 10, "rate": 150, "amount": 1500, "description": "July"},
                {"item": "Product A", "amount": 200},
            ],
        }
    )
    xml = build_invoice_add_rq(invoice)
    assert "<CustomerRef><FullName>Acme Corp</FullName></CustomerRef>" in xml
    assert "<RefNumber>INV-1001</RefNumber>" in xml
    assert "CurrencyRef" not in xml
    assert xml.count("<InvoiceLineAdd>") == 2
    assert "<ItemRef><FullName>Consulting</FullName></ItemRef>" in xml
    assert "<Quantity>10</Quantity>" in xml
    assert "<Rate>150.00</Rate>" in xml
    assert "<Amount>1500.00</Amount>" in xml
    assert "<Amount>200.00</Amount>" in xml


def test_build_invoice_add_rq_multicurrency():
    invoice = Invoice.model_validate(
        {
            "ref_number": "INV-2",
            "customer": "Acme Corp",
            "date": "2026-07-01",
            "currency": "CHF",
            "exchange_rate": 1.0962,
            "lines": [{"item": "Consulting", "amount": 500}],
        }
    )
    xml = build_invoice_add_rq(invoice)
    assert "<CurrencyRef><FullName>Swiss Franc</FullName></CurrencyRef>" in xml
    assert "<ExchangeRate>1.0962</ExchangeRate>" in xml


def test_parse_invoice_add_rs_success():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <InvoiceAddRs statusCode="0" statusMessage="Status OK">
        <InvoiceRet><TxnID>INV-TXN-1</TxnID></InvoiceRet>
      </InvoiceAddRs>
    </QBXMLMsgsRs></QBXML>"""
    result = parse_invoice_add_rs(response)
    assert result == {"status_code": 0, "status_message": "Status OK", "txn_id": "INV-TXN-1"}


def test_invoice_query_no_match():
    request = build_invoice_query_rq("INV-1001", "Acme Corp")
    assert "<RefNumber>INV-1001</RefNumber>" in request
    assert "<EntityFilter><FullName>Acme Corp</FullName></EntityFilter>" in request
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs><InvoiceQueryRs></InvoiceQueryRs></QBXMLMsgsRs></QBXML>"""
    assert parse_invoice_query_rs(response) == []


def test_invoice_query_one_match():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <InvoiceQueryRs>
        <InvoiceRet>
          <TxnID>80000012-1234567890</TxnID>
          <RefNumber>INV-1001</RefNumber>
          <CustomerRef><FullName>Acme Corp</FullName></CustomerRef>
          <BalanceRemaining>1500.00</BalanceRemaining>
        </InvoiceRet>
      </InvoiceQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    results = parse_invoice_query_rs(response)
    assert len(results) == 1
    assert results[0]["txn_id"] == "80000012-1234567890"
    assert results[0]["customer"] == "Acme Corp"


def test_invoice_query_many_matches():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <InvoiceQueryRs>
        <InvoiceRet><TxnID>t1</TxnID><RefNumber>INV-1</RefNumber></InvoiceRet>
        <InvoiceRet><TxnID>t2</TxnID><RefNumber>INV-1</RefNumber></InvoiceRet>
      </InvoiceQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    assert len(parse_invoice_query_rs(response)) == 2


# -- Bills --------------------------------------------------------------

def test_build_bill_add_rq():
    bill = Bill.model_validate(
        {
            "ref_number": "B-100",
            "vendor": "Acme Supplier",
            "date": "2026-07-01",
            "currency": "CHF",
            "exchange_rate": 1.0962,
            "lines": [
                {"account": "Office Supplies", "amount": 250, "description": "Paper"},
                {"account": "Rent", "amount": 1000},
            ],
        }
    )
    xml = build_bill_add_rq(bill)
    assert "<VendorRef><FullName>Acme Supplier</FullName></VendorRef>" in xml
    assert "<RefNumber>B-100</RefNumber>" in xml
    assert "<CurrencyRef><FullName>Swiss Franc</FullName></CurrencyRef>" in xml
    assert "<ExchangeRate>1.0962</ExchangeRate>" in xml
    assert xml.count("<ExpenseLineAdd>") == 2
    assert "<AccountRef><FullName>Office Supplies</FullName></AccountRef>" in xml
    assert "<Amount>250.00</Amount>" in xml
    assert "<Memo>Paper</Memo>" in xml


def test_parse_bill_add_rs_error():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <BillAddRs statusCode="3140" statusMessage="Account not found">
      </BillAddRs>
    </QBXMLMsgsRs></QBXML>"""
    result = parse_bill_add_rs(response)
    assert result["status_code"] == 3140
    assert result["txn_id"] is None


def test_bill_query_vendor_scoped():
    request = build_bill_query_rq("B-100", "Acme Supplier")
    assert "<RefNumber>B-100</RefNumber>" in request
    assert "<EntityFilter><FullName>Acme Supplier</FullName></EntityFilter>" in request
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <BillQueryRs>
        <BillRet>
          <TxnID>80000020-1234567890</TxnID>
          <RefNumber>B-100</RefNumber>
          <VendorRef><FullName>Acme Supplier</FullName></VendorRef>
          <AmountDue>250.00</AmountDue>
        </BillRet>
      </BillQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    results = parse_bill_query_rs(response)
    assert results[0]["txn_id"] == "80000020-1234567890"
    assert results[0]["vendor"] == "Acme Supplier"


# -- Payments (linked via AppliedToTxnAdd) --------------------------------

def test_build_receive_payment_add_rq_linked_to_invoices():
    payment = CustomerPayment.model_validate(
        {
            "payment_id": "p1",
            "customer": "Acme Corp",
            "date": "2026-07-15",
            "deposit_to_account": "Undeposited Funds",
            "currency": "USD",
            "exchange_rate": 1.36,
            "applications": [
                {"invoice_ref": "INV-1001", "amount": 1500},
                {"invoice_ref": "INV-1002", "amount": 200},
            ],
        }
    )
    txn_ids = {"INV-1001": "80000012-1234567890", "INV-1002": "80000013-1234567890"}
    xml = build_receive_payment_add_rq(payment, txn_ids)
    assert "<CustomerRef><FullName>Acme Corp</FullName></CustomerRef>" in xml
    assert "<TotalAmount>1700.00</TotalAmount>" in xml
    assert "<CurrencyRef><FullName>US Dollar</FullName></CurrencyRef>" in xml
    assert "<ExchangeRate>1.36</ExchangeRate>" in xml
    assert "<DepositToAccountRef><FullName>Undeposited Funds</FullName></DepositToAccountRef>" in xml
    assert xml.count("<AppliedToTxnAdd>") == 2
    assert "<TxnID>80000012-1234567890</TxnID><PaymentAmount>1500.00</PaymentAmount>" in xml
    assert "<TxnID>80000013-1234567890</TxnID><PaymentAmount>200.00</PaymentAmount>" in xml


def test_parse_receive_payment_add_rs_finds_top_level_txn_id_not_applied_ones():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <ReceivePaymentAddRs statusCode="0" statusMessage="Status OK">
        <ReceivePaymentRet>
          <TxnID>PMT-TXN-1</TxnID>
          <AppliedToTxnRet><TxnID>INV-TXN-999</TxnID></AppliedToTxnRet>
        </ReceivePaymentRet>
      </ReceivePaymentAddRs>
    </QBXMLMsgsRs></QBXML>"""
    result = parse_receive_payment_add_rs(response)
    assert result["txn_id"] == "PMT-TXN-1"


def test_build_bill_payment_check_add_rq_with_check_number():
    payment = VendorPayment.model_validate(
        {
            "payment_id": "vp1",
            "vendor": "Acme Supplier",
            "date": "2026-07-15",
            "bank_account": "OCBC Bank (USD)",
            "check_number": "1234",
            "applications": [{"bill_ref": "B-100", "amount": 250}],
        }
    )
    xml = build_bill_payment_check_add_rq(payment, {"B-100": "80000020-1234567890"})
    assert "<PayeeEntityRef><FullName>Acme Supplier</FullName></PayeeEntityRef>" in xml
    assert "<BankAccountRef><FullName>OCBC Bank (USD)</FullName></BankAccountRef>" in xml
    assert "<RefNumber>1234</RefNumber>" in xml
    assert "<IsToBePrinted>false</IsToBePrinted>" in xml
    assert "<TxnID>80000020-1234567890</TxnID><PaymentAmount>250.00</PaymentAmount>" in xml


def test_build_bill_payment_check_add_rq_without_check_number_marks_to_be_printed():
    payment = VendorPayment.model_validate(
        {
            "payment_id": "vp2",
            "vendor": "Acme Supplier",
            "date": "2026-07-15",
            "bank_account": "OCBC Bank (USD)",
            "applications": [{"bill_ref": "B-100", "amount": 250}],
        }
    )
    xml = build_bill_payment_check_add_rq(payment, {"B-100": "80000020-1234567890"})
    assert "<IsToBePrinted>true</IsToBePrinted>" in xml
    assert "<RefNumber>" not in xml


def test_parse_bill_payment_check_add_rs_success():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <BillPaymentCheckAddRs statusCode="0" statusMessage="Status OK">
        <BillPaymentCheckRet><TxnID>BPC-TXN-1</TxnID></BillPaymentCheckRet>
      </BillPaymentCheckAddRs>
    </QBXMLMsgsRs></QBXML>"""
    result = parse_bill_payment_check_add_rs(response)
    assert result["txn_id"] == "BPC-TXN-1"
