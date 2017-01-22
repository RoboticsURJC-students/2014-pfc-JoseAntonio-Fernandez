from __future__ import print_function
__author__ = 'Jose Antonio Fernandez Casillas'
#Version 1.0


import threading,time,sys,traceback
import jderobot,Ice
from pymavlink import mavutil, quaternion, mavwp
from pymavlink.dialects.v10 import ardupilotmega as mavlink
from interfaces.Pose3DI import  Pose3DI
from interfaces.NavdataI import NavdataI



class Server:

    def __init__(self, port, baudrate):
        """
        In the constructor we create the connection to the APM device
        and start 2 thread one for the comuniction with the device and the other
        one to serv it on Ice
        @:type port: text
        @:param port: port to establish the connection
        @:type baudrate: text
        @:param baudrate: onnection speed
        """

        #control variables to identify if is real the measure
        self.attitudeStatus = 0
        self.altitudeStatus = 0
        self.gpsStatus = 0
        self.lastSentHeartbeat = 0
        self.battery_remainingStatus = 0
        self.rawIMUStatus = 0
        self.scaled_presureStatus = 0

        self.pose3D = Pose3DI(0,0,0,0,0,0,0,0)
        self.navdata = NavdataI()

        #TODO cambiar el Pose3DData por un Pose 3D

        #connect to tu the APM
        self.master = mavutil.mavlink_connection(port, baudrate, autoreconnect=True)
        print('Connection established to device')

        self.master.wait_heartbeat()
        print("Heartbeat Recieved")

        #Thread to mannage the AMP messages
        MsgHandler = threading.Thread(target=self.mavMsgHandler, args=(self.master,), name='msg_Handler')
        print('Initiating server...')
        #MsgHandler.daemon = True
        MsgHandler.start()

        #Thread to serve Pose3D with the attitude
        PoseTheading = threading.Thread(target=self.openPose3DChannel, args=(self.pose3D,), name='Pose_Theading')
        PoseTheading.daemon = True
        PoseTheading.start()

        '''
        #Thread to recieve Pose3D with a waypoint
        PoseTheading = threading.Thread(target=self.openPose3DChannelWP, name='WayPoint_client')
        PoseTheading.daemon = True
        PoseTheading.start()
        '''

        # Thread to serve Navdata with the all navigation info
        CMDVelTheading = threading.Thread(target=self.openNavdataChannel, args=(self.navdata,), name='Navdata_Theading')
        CMDVelTheading.daemon = True
        CMDVelTheading.start()


    def mavMsgHandler(self, m):
        """
        Funtion who handle the mavLink's messages received and refresh the attitude
        :param m: mavLink Connector
        :return: none
        """
        while True:
            msg = m.recv_msg()
            # print msg
            # send heartbeats to autopilot
            if time.time() - self.lastSentHeartbeat > 1.0:
                self.master.mav.heartbeat_send(mavlink.MAV_TYPE_GCS, mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                self.lastSentHeartbeat = time.time()

            if msg is None or msg.get_type() == "BAD_DATA":
                time.sleep(0.01)
                continue

            '''
            legacy seems don't needed
            # enable data streams after start up - can't see another way of doing this.
            if msg.get_type() == "STATUSTEXT" and "START" in msg.text:
                self.setDataStreams(mavlink.MAV_DATA_STREAM_EXTRA1)
                self.setDataStreams(mavlink.MAV_DATA_STREAM_EXTENDED_STATUS)
                self.setDataStreams(mavlink.MAV_DATA_STREAM_EXTRA2)
                self.setDataStreams(mavlink.MAV_DATA_STREAM_POSITION)
                #self._master.mav.request_data_stream_send(0, 0, mavutil.mavlink.MAV_DATA_STREAM_ALL,4, 1)
            '''
            #refresh the attitude
            self.refreshAPMPose3D()
            self.refreshAPMnavdata()

    def refreshAPMPose3D(self):
        """
        Funtion to refresh the Pose3D class atribute
        The altitude is recovered to but already is not used
        :return: none
        """

        #get attitude of APM
        if 'ATTITUDE' not in self.master.messages:
            self.attitudeStatus = 1
            q=[0,0,0,0]
        else:
            attitude = self.master.messages['ATTITUDE']
            #print(attitude)
            yaw = getattr(attitude,"yaw")
            pitch = getattr(attitude,"pitch")
            roll = getattr(attitude,"roll")
            q = quaternion.Quaternion([roll, pitch, yaw])

        #get altitude of APM
        altitude = self.master.field('VFR_HUD', 'alt', None)
        if altitude is None:
            self.altitudeStatus = 1

        #get GPS position from APM
        latitude = 0
        longitude = 0
        if 'GPS_RAW_INT' not in self.master.messages:
            self.gpsStatus = 1
        else:
            gps = self.master.messages['GPS_RAW_INT']
            # TODO por que dividir entre 10e6

            latitude = getattr(gps,"lat")/ 10e6;
            longitude = getattr(gps,"lon") / 10e6;
            self.GPS_fix_type = getattr(gps,"fix_type")

        # refresh the pose3D
        data = jderobot.Pose3DData
        data.x = latitude
        data.y = longitude
        data.z = altitude
        data.h = altitude
        data.q0 = q.__getitem__(0)
        data.q1 = q.__getitem__(1)
        data.q2 = q.__getitem__(2)
        data.q3 = q.__getitem__(3)
        self.pose3D.setPose3DData(data)

    def refreshAPMnavdata(self):
        """
        Funtion to refresh the Pose3D class atribute
        The altitude is recovered to but already is not used
        :return: none
        """
        battery_remaining = 0
        rawIMU = {}
        scaled_presure = {}
        wind = {}
        global_position = {}


        #get battery_remaining
        if 'SYS_STATUS' not in self.master.messages:
            self.battery_remainingStatus = 1
        else:
            stats = self.master.messages['SYS_STATUS']
            battery_remaining = getattr(stats,"battery_remaining")
            print("Battery lebel " +str(battery_remaining)+ " %")

        #get RAW_IMU
        if 'RAW_IMU' not in self.master.messages:
            self.rawIMUStatus = 1
        else:
            rawIMU = self.master.messages['RAW_IMU']

        #get SCALED PRESSURE
        if 'SCALED_PRESSURE' not in self.master.messages:
            self.scaled_presureStatus = 1
        else:
            scaled_presure = self.master.messages['SCALED_PRESSURE']

        #get WIND
        if 'WIND' not in self.master.messages:
            self.gpsStatus = 1
        else:
            wind = self.master.messages['WIND']

        #get GLOBAL_POSITION_INT
        if 'GLOBAL_POSITION_INT' not in self.master.messages:
            self.gpsStatus = 1
        else:
            global_position = self.master.messages['GLOBAL_POSITION_INT']

        # refresh the navdata
        ndata = jderobot.NavdataData()
        #TODO setear los valores del NavData
        ndata.batteryPercent = battery_remaining
        try:
            ndata.pressure = getattr(scaled_presure, "press_abs")
        except:
            print (str(scaled_presure))
        try:
            ndata.temp = getattr(scaled_presure, "temperature")/100
        except:
            print(str(scaled_presure))
        try:
            ndata.windSpeed = getattr(wind, "speed")
        except:
            print(str(wind))
        try:
            ndata.windAngle = getattr(wind, "direction")
        except:
            print(str(wind))
        try:
            ndata.vx = getattr(global_position, "vx")
        except:
            print(str(global_position))
        try:
            ndata.vy = getattr(global_position, "vy")
        except:
            print(str(global_position))
        try:
            ndata.vz = getattr(global_position, "vz")
        except:
            print(str(global_position))
        try:
            ndata.rotx = getattr(rawIMU, "xgyro")
        except:
            print(str(rawIMU))
        try:
            ndata.roty = getattr(rawIMU, "ygyro")
        except:
            print(str(rawIMU))
        try:
            ndata.rotz = getattr(rawIMU, "zgyro")
        except:
            print(str(rawIMU))
        try:
            ndata.ax = getattr(rawIMU, "xacc")
        except:
            print(str(rawIMU))
        try:
            ndata.ay = getattr(rawIMU, "yacc")
        except:
            print(str(rawIMU))
        try:
            ndata.az = getattr(rawIMU, "zacc")
        except:
            print(str(rawIMU))
        try:
            ndata.magx = getattr(rawIMU, "xmag")
        except:
            print(str(rawIMU))
        try:
            ndata.magy = getattr(rawIMU, "ymag")
        except:
            print(str(rawIMU))
        try:
            ndata.magz = getattr(rawIMU, "zmag")
        except:
            print(str(rawIMU))
        self.navdata.setNavdata(ndata)


    '''FROZEN
    def flyTo(self, lat, lon, alt):
        #TODO revisar con el codigo de Jorge Cano/Vela
        #TODO cambiar signatura por navigateTo(self, pose3D)
        #																				seqfrm cmd                          cur at p1 p2 p3 p4  x    y    z
        self.master.mav.mission_item_send(self.mav.target_system, self.mav.target_component, 0, 0, mavlink.MAV_CMD_NAV_WAYPOINT, 2, 0, 5, 0, 0, 0, lat, lon, alt)
    '''

    def oneWaypointMission(self, pose3D):
        '''
        Create a list os one pose3D. This funtion was created to support mission when only a pose3D is recieved.
        At the moment Jderobot does not support a list of Pose3D served in Ice we need another interface
        :param pose3D: a waypoint recieved in Pose3D interface
        :return: none
        '''
        listM = []
        listM.append(pose3D)
        self.setMission(listM)

    def setMission(self, pose3Dwaypoints):
        '''
        SetUp a mission with a list of waypoints, based on Colorado University Boulder Code
        http://www.colorado.edu/recuv/2015/05/25/mavlink-protocol-waypoints
        :param pose3Dwaypoints: list of waypoints to the mission
        :return: None
        '''
        wp = mavwp.MAVWPLoader()
        frame = mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT
        radius = 20
        N = pose3Dwaypoints.length
        for i in range(N):
            navData = jderobot.Pose3DData()
            navData.setPose3DData(pose3Dwaypoints[i].getPose3DData)
            wp.add(mavutil.mavlink.MAVLink_mission_item_message(self.master.target_system,
                                                                self.master.target_component,
                                                                i,
                                                                frame,
                                                                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                                                                0, 0, 0, radius, 0, 0,
                                                                navData.x, navData.y, navData.h))
        self.master.waypoint_clear_all_send()
        self.master.waypoint_count_send(wp.count())


        for i in range(wp.count()):
            msg = self.master.recv_match(type=['MISSION_REQUEST'], blocking=True)
            self.master.mav.send(wp.wp(msg.seq))
            print ('Sending waypoint {0}'.format(msg.seq))

        self.master.set_mode_auto() # arms and start mission I thought


    # ------------ Ice clients servers ---------------

    def openPose3DChannel(self, pose3D):
        """
        Open a Ice Server to serve Pose3D objects
        :return: none
        """

        status = 0
        ic = None
        # recovering the attitude
        Pose2Tx = pose3D
        print('Open the Ice Server Channel')
        try:
            ic = Ice.initialize(sys.argv)
            adapter = ic.createObjectAdapterWithEndpoints("Pose3DAdapter", "default -p 9998")
            object = Pose2Tx
            # print object.getPose3DData()
            adapter.add(object, ic.stringToIdentity("ardrone_pose3d")) #ardrone_pose3d  Pose3D
            adapter.activate()
            ic.waitForShutdown()
        except:
            traceback.print_exc()
            status = 1
        if ic:
            # Clean up
            try:
                ic.destroy()
            except:
                traceback.print_exc()
                status = 1

        sys.exit(status)


    def openPose3DChannelWP(self):
        '''
        Open a Pose3D client to recieve Pose3D with a waypoint
        :return:  mone
        '''
        status = 0
        ic = None
        try:
            ic = Ice.initialize(sys.argv)
            base = ic.stringToProxy("Pose3D:default -p 9998")
            datos = jderobot.Pose3DPrx.checkedCast(base)
            print(datos)
            if not datos:
                raise RuntimeError("Invalid proxy")

            while True:
                time.sleep(1)
                data = datos.getPose3DData()
                print(data)
                self.oneWaypointMission(data)
        except:
            traceback.print_exc()
            status = 1

        if ic:
            # Clean up
            try:
                ic.destroy()
            except:
                traceback.print_exc()
                status = 1

        sys.exit(status)



    def openNavdataChannel(self, navdata):
        '''
        Open a Ice Server to serve all the navigation data
        :return:
        '''
        status = 0
        ic = None
        Navdata2Tx = navdata

        try:
            ic = Ice.initialize(sys.argv)
            adapter = ic.createObjectAdapterWithEndpoints("navdata_adapter", "default -p 9996")
            object = Navdata2Tx
            adapter.add(object, ic.stringToIdentity("ardrone_navdata"))
            adapter.activate()
            ic.waitForShutdown()
        except:
            traceback.print_exc()
            status = 1

        if ic:
            # Clean up
            try:
                ic.destroy()
            except:
                traceback.print_exc()
                status = 1

        sys.exit(status)




