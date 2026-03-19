from flask import Flask, jsonify, request
import os
from datetime import date
from pathlib import Path

import requests

from garth.exc import GarthException, GarthHTTPError
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

app = Flask(__name__)
global client
client = None
live = False

if live:
    gemail_path = '/run/secrets/garmin_email.txt'
    gpassword_path = '/run/secrets/garmin_password.txt'
    genv_path = '/root/.garminconnect'
else:
    gemail_path = 'secrets/garmin_email.txt'
    gpassword_path = 'secrets/garmin_password.txt'
    genv_path = 'tokens'
    
def init_garmin() -> Garmin | None:
    """Initialize Garmin API with authentication and token management."""
    # Configure token storage
    tokenstore_path = Path(genv_path).expanduser()
    # Check if token files exist
    if tokenstore_path.exists():
        token_files = list(tokenstore_path.glob("*.json"))
        if token_files:
            pass
        else:
            pass
    else:
        pass

    # First try to login with stored tokens
    try:
        garmin = Garmin()
        garmin.login(str(tokenstore_path))
        return garmin

    except (
        FileNotFoundError,
        GarthHTTPError,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
    ):
        pass

    # Loop for credential entry with retry on auth failure
    while True:
        try:
            # Get credentials
            email = open(gemail_path).read().strip()
            password = open(gpassword_path).read().strip()

            garmin = Garmin(
                email=email, password=password, is_cn=False, return_on_mfa=True
            )
            result1, result2 = garmin.login()

            if result1 == "needs_mfa":
                mfa_code = input("Please enter your MFA code: ")

                try:
                    garmin.resume_login(result2, mfa_code)

                except GarthHTTPError as garth_error:
                    # Handle specific HTTP errors from MFA
                    error_str = str(garth_error)
                    if "429" in error_str and "Too Many Requests" in error_str:
                        sys.exit(1)
                    elif "401" in error_str or "403" in error_str:
                        continue
                    else:
                        # Other HTTP errors - don't retry
                        sys.exit(1)

                except GarthException:
                    continue

            # Save tokens for future use
            garmin.garth.dump(str(tokenstore_path))
            return garmin

        except GarminConnectAuthenticationError:
            # Continue the loop to retry
            continue

        except (
            FileNotFoundError,
            GarthHTTPError,
            GarminConnectConnectionError,
            requests.exceptions.HTTPError,
        ):
            return None

        except KeyboardInterrupt:
            return None

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
    client = init_garmin()
    app.run(host='0.0.0.0', port=8080, debug=False)