# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

from eventlog_pro import log_event


def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.


print(log_event(
    app="api",
    category="webhook",
    sub_category="zoho3",
    event_type="error",
    event_code="SIGNATURE_MISMATCH",
    entity="test",
    remarks="Invalid webhook signature",
    data={"path": "some path", "ip": "this is my ip"},
    created_by="system",
))

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('eventlog-pro')

# eventlog_pro is not configured; falling back to sqlite:///./events.db,
# which will create C:\Users\gal20\PycharmProjects\test20260814-eventlog-pro\events.db.
# Set EVENTLOG_DSN or call eventlog_pro.configure(dsn=...) to choose a destination.
