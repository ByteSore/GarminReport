from flask import Flask, jsonify, request
from garminconnect import Garmin
import os
from datetime import date

app = Flask(__name__)
client = None

def init_garmin():
    global client
    try:
        email = open('/run/secrets/garmin_email').read().strip()
        password = open('/run/secrets/garmin_password').read().strip()
        client = Garmin(email, password)
        client.garth.load('/root/.garminconnect')
        client.display_name = client.garth.profile['displayName']
        print(f"Tokens geladen OK, gebruiker: {client.display_name}")
    except Exception as e:
        print(f"Garmin login mislukt: {e}")

# ── Bestaande routes ──────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'ingelogd': client is not None})

@app.route('/activiteiten')
def activiteiten():
    start = request.args.get('start', 0, type=int)
    limit = request.args.get('limit', 10, type=int)
    return jsonify(client.get_activities(start, limit))

@app.route('/stappen')
def stappen():
    datum = request.args.get('datum')
    return jsonify(client.get_steps_data(datum))

@app.route('/slaap')
def slaap():
    datum = request.args.get('datum')
    return jsonify(client.get_sleep_data(datum))

@app.route('/hartslag')
def hartslag():
    datum = request.args.get('datum')
    return jsonify(client.get_heart_rates(datum))

@app.route('/hrv')
def hrv():
    datum = request.args.get('datum')
    return jsonify(client.get_hrv_data(datum))

@app.route('/stress')
def stress():
    datum = request.args.get('datum')
    return jsonify(client.get_stress_data(datum))

@app.route('/stats')
def stats():
    datum = request.args.get('datum')
    return jsonify(client.get_stats(datum))

@app.route('/gewicht')
def gewicht():
    datum = request.args.get('datum')
    if datum:
        return jsonify(client.get_weigh_ins(datum, datum))
    start = request.args.get('start', '2024-01-01')
    eind  = request.args.get('eind',  date.today().isoformat())
    return jsonify(client.get_body_composition(start, eind))

# ── Nieuwe routes ─────────────────────────────────────────────────────────────

@app.route('/training-readiness')
def training_readiness():
    """
    Fenix 8: Training Readiness score 0-100 + status + feedback.
    Geeft lijst terug; laatste entry is meest actueel.
    """
    datum = request.args.get('datum', date.today().isoformat())
    try:
        return jsonify(client.get_training_readiness(datum))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/training-status')
def training_status():
    """
    Fenix 8: Training Status (Productive / Maintaining / Overreaching etc.)
    + acuut/chronisch belasting + VO2max precise + fitness age.
    """
    datum = request.args.get('datum', date.today().isoformat())
    try:
        return jsonify(client.get_training_status(datum))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vo2max')
def vo2max():
    """
    Fenix 8: VO2max + fitness age via get_max_metrics(date).
    Ondersteunt ?datum= voor 1 dag of ?startDatum=&eindDatum= voor een reeks.
    """
    datum       = request.args.get('datum')
    start_datum = request.args.get('startDatum')
    eind_datum  = request.args.get('eindDatum')
    resultaten  = []

    if datum:
        try:
            r = client.get_max_metrics(datum)
            resultaten.append({'calendarDate': datum, 'data': r})
        except Exception as e:
            resultaten.append({'calendarDate': datum, 'error': str(e)})

    elif start_datum and eind_datum:
        from datetime import datetime, timedelta
        s = datetime.strptime(start_datum, '%Y-%m-%d').date()
        e = datetime.strptime(eind_datum,  '%Y-%m-%d').date()
        while s <= e:
            ds = s.isoformat()
            try:
                r = client.get_max_metrics(ds)
                resultaten.append({'calendarDate': ds, 'data': r})
            except Exception as ex:
                resultaten.append({'calendarDate': ds, 'error': str(ex)})
            s += timedelta(days=1)

    else:
        ds = date.today().isoformat()
        try:
            r = client.get_max_metrics(ds)
            resultaten.append({'calendarDate': ds, 'data': r})
        except Exception as e:
            resultaten.append({'calendarDate': ds, 'error': str(e)})

    return jsonify(resultaten)

@app.route('/race-predictions')
def race_predictions():
    """
    Fenix 8: Voorspelde race tijden 5K / 10K / HM / Marathon.
    Geen datumparameter nodig.
    """
    try:
        return jsonify(client.get_race_predictions())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/hartslagzones')
def hartslagzones():
    """
    Dagelijkse hartslag zone verdeling.
    get_heart_rates(datum) bevat heartRateZones als die dag data heeft.
    """
    datum = request.args.get('datum', date.today().isoformat())
    try:
        r = client.get_heart_rates(datum)
        zones = r.get('heartRateZones', []) if isinstance(r, dict) else []
        return jsonify({
            'datum': datum,
            'heartRateZones': zones,
            'raw': r
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/activiteit-zones')
def activiteit_zones():
    """
    HR zones voor een specifieke activiteit (nauwkeuriger dan daggemiddelde).
    Gebruik: /activiteit-zones?id=<activityId>
    """
    activity_id = request.args.get('id', type=int)
    if not activity_id:
        return jsonify({'error': 'id parameter verplicht'}), 400
    try:
        return jsonify(client.get_activity_hr_in_timezones(activity_id))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/fitnessleeftijd')
def fitnessleeftijd():
    """
    Fitness Age (apart van get_max_metrics).
    """
    datum = request.args.get('datum', date.today().isoformat())
    try:
        return jsonify(client.get_fitnessage_data(datum))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/persoonlijke-records')
def persoonlijke_records():
    """
    Persoonlijke records per afstand/discipline.
    """
    try:
        return jsonify(client.get_personal_record())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_garmin()
    app.run(host='0.0.0.0', port=8080, debug=False)
