$(document).ready(function () {
    let SdateVal = $('#Sdate').val();
    let EDateVal = $('#Edate').val();

    if (SdateVal === '') {
        $('#Sdate').val(moment().subtract(1, 'd').format('YYYY-MM-DD'));
    }

    if (EDateVal === '') {
        $('#Edate').val(moment().subtract(1, 'd').format('YYYY-MM-DD'));
    }

    $('#date-range').daterangepicker(
        {
            timePicker: false,
            opens: 'left',
            ranges: {
                Today: [moment().startOf('day'), moment().endOf('day')],
                Yesterday: [
                    moment().subtract(1, 'days').startOf('day'),
                    moment().subtract(1, 'days').endOf('day'),
                ],
                'Last 2 Days': [
                    moment().subtract(2, 'days').startOf('day'),
                    moment().subtract(2, 'days').endOf('day'),
                ],
                'Last 7 Days': [
                    moment().subtract(7, 'days').startOf('day'),
                    moment().subtract(1, 'days').endOf('day'),
                ],
                'Last 14 Days': [
                    moment().subtract(13, 'days').startOf('day'),
                    moment().endOf('day'),
                ],
                'This Month': [
                    moment().startOf('month').startOf('day'),
                    moment().endOf('month').endOf('day'),
                ],
                'Last Month': [
                    moment().subtract(1, 'months').startOf('month'),
                    moment().subtract(1, 'months').endOf('month'),
                ],
            },
            locale: {
                format: 'YYYY-MM-DD',
            },
            maxDate: moment().format('YYYY-MM-DD')
        },
        function (start, end) {
            $('#Sdate').val(start.format('YYYY-MM-DD'));
            $('#Edate').val(end.format('YYYY-MM-DD'));
        }
    );
    var drp = $('#date-range').data('daterangepicker');
    drp.setStartDate($('#Sdate').val());
    drp.setEndDate($('#Edate').val());
    //App filter

    let options = {
        valueNames: ['name-app'],
    };
});

document.addEventListener('alpine:init', () => {
    Alpine.data(
        'dropdownCustom',
        (initSelect = [], initInclude = true, initexclude = false) => ({
            open: false,
            listSelect: [],
            listGameSelect: [],
            include: true,
            exclude: false,
            searchKey: '',
            countries: [],
            async init() {
                setTimeout(() => {
                    console.log(initSelect);
                    initSelect.forEach((item, index) => {
                        this.addToList(item);
                    });

                    this.include = initInclude;
                    this.exclude = initexclude;
                }, 0);
            },
            addInclude() {
                this.include = true;
                this.exclude = false;
            },
            addExclude() {
                this.include = false;
                this.exclude = true;
            },
            toggle() {
                this.open = !this.open;
            },
            addToList(value) {
                this.listSelect.push(value);
                this.listGameSelect.push({
                    name: $(
                        '#' + new String(value).replaceAll('.', '-')
                    ).text(),
                    id: value,
                });
            },
            removeFromList(value) {
                let index = this.listSelect.indexOf(value);
                this.listSelect.splice(index, 1);

                this.listGameSelect.forEach((item, index) => {
                    if (item.id === value) {
                        this.listGameSelect.splice(index, 1);
                    }
                });
            },
            checkInList(value) {
                return this.listSelect.includes(value);
            },
            displaySelect(defaultText) {
                return this.listSelect.length > 0
                    ? (this.include ? 'Include: ' : 'Exclude: ') +
                    this.listSelect.length +
                    ' Selected'
                    : defaultText;
            },
            displaySelectNormal(defaultText) {
                return this.listSelect.length > 0
                    ? this.listSelect.length + ' Selected'
                    : defaultText;
            },
            reset() {
                this.listSelect = [];
                this.listGameSelect = [];
                this.include = true;
                this.exclude = false;
                this.searchKey = '';
            },
            formatResult() {
                return this.listSelect.map((item, index) => {
                    return item
                });
            },
            normalResult() {
                return this.listSelect;
            },
            displaySelectBreak(defaultText) {
                let newSelects = this.listSelect.map((item, index) => {
                    switch (item) {
                        case 'game_name':
                            return 'Game';
                        case 'date':
                            return 'Day';
                        case 'country_name':
                            return 'Country';
                        case 'platform':
                            return 'Platform';
                        case 'network':
                            return 'Network';
                        case 'company_name':
                            return 'Company';
                    }
                });

                return this.listSelect.length > 0
                    ? 'Break by: ' + newSelects.join(', ')
                    : defaultText;
            },
        })
    );
});