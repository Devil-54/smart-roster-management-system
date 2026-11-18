from datetime import date, datetime, timedelta


def rule_operates_on(rule, target_date: date, holiday_dates: set[date]) -> bool:
    if (
        rule.day_of_week != target_date.weekday()
        or not rule.is_operating
        or rule.min_staff_required <= 0
    ):
        return False

    calendar_type = rule.operating_calendar or (
        rule.brand.calendar_type if rule.brand else '365_DAYS'
    )
    is_holiday = target_date in holiday_dates

    if is_holiday and calendar_type in ('DAILY_EXCEPT_HOLIDAYS', 'SUNDAYS_HOLIDAYS_OFF'):
        return False
    if target_date.weekday() == 6 and calendar_type == 'SUNDAYS_HOLIDAYS_OFF':
        return False
    return True


def shift_interval(target_date: date, shift_type):
    start_time = datetime.strptime(shift_type.start_time, '%H:%M').time()
    end_time = datetime.strptime(shift_type.end_time, '%H:%M').time()
    start = datetime.combine(target_date, start_time)
    end = datetime.combine(target_date, end_time)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def shifts_overlap(first_date: date, first_shift, second_date: date, second_shift) -> bool:
    first_start, first_end = shift_interval(first_date, first_shift)
    second_start, second_end = shift_interval(second_date, second_shift)
    return first_start < second_end and second_start < first_end
